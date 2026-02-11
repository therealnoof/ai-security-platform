#!/usr/bin/env python3
"""AI Security Research Agent — generates weekly digest via Claude with web search."""

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import yaml

# ── Constants ────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 8192
MAX_RETRIES = 3
BACKOFF_SECONDS = [60, 120, 240]
TURN_DELAY = 65  # seconds between API calls — just over 1 min to reset the token window

REPO_ROOT = Path(__file__).resolve().parent.parent
DIGESTS_DIR = REPO_ROOT / "src" / "content" / "digests"
LOGS_DIR = REPO_ROOT / "agent-logs"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
IMAGES_DIR = REPO_ROOT / "public" / "images" / "digests"

REQUIRED_FRONTMATTER_FIELDS = {
    "title": str,
    "description": str,
    "pubDate": (str, datetime),
    "weekNumber": int,
    "year": int,
    "highlights": list,
    "draft": bool,
}


# ── Week Metadata ────────────────────────────────────────────────────────────


def compute_week_metadata() -> dict:
    """Compute ISO week number, year, date range, and filename for the current digest."""
    today = datetime.now(timezone.utc).date()
    iso_year, iso_week, _ = today.isocalendar()

    # The digest covers the previous Monday–Sunday
    # Find the most recent Monday (start of the ISO week we're publishing for)
    days_since_monday = today.weekday()  # 0=Mon, 6=Sun
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(weeks=1)
    last_sunday = last_monday + timedelta(days=6)

    # The week number for the digest is the ISO week of last_monday
    digest_year, digest_week, _ = last_monday.isocalendar()

    pub_date = today.isoformat()
    date_range = f"{last_monday.strftime('%B %d')} – {last_sunday.strftime('%B %d, %Y')}"
    filename = f"{digest_year}-week-{digest_week:02d}.md"

    return {
        "week_number": digest_week,
        "year": digest_year,
        "pub_date": pub_date,
        "date_range": date_range,
        "filename": filename,
    }


# ── Prompt Loading ───────────────────────────────────────────────────────────


def load_prompt(name: str, **kwargs) -> str:
    """Load a prompt template and fill in variables."""
    path = PROMPTS_DIR / name
    template = path.read_text()
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template


# ── API Calls ────────────────────────────────────────────────────────────────


def api_call_with_retries(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    """Wrapper around client.messages.create that retries on rate limits and 5xx errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            wait = BACKOFF_SECONDS[attempt]
            print(f"    ⚠ Rate limited (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s...")
            time.sleep(wait)
            if attempt == MAX_RETRIES - 1:
                raise
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                wait = BACKOFF_SECONDS[attempt]
                print(f"    ⚠ Server error {e.status_code} (attempt {attempt + 1}/{MAX_RETRIES}), waiting {wait}s...")
                time.sleep(wait)
                if attempt == MAX_RETRIES - 1:
                    raise
            else:
                raise


def run_research_pass(client: anthropic.Anthropic, system_prompt: str) -> tuple[str, dict]:
    """Run the research pass with web search. Returns (digest_text, usage_stats)."""
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    messages = [
        {
            "role": "user",
            "content": "Research this week's AI security news and produce the digest now. "
            "Use web search across all 7 categories. "
            "Your final output must be ONLY the Markdown file starting with --- (frontmatter). "
            "No preamble or commentary.",
        }
    ]

    turn = 0
    while True:
        # Pause before every call except the first to stay under token-per-minute limits
        if turn > 0:
            print(f"    … pausing {TURN_DELAY}s between turns (rate limit headroom)")
            time.sleep(TURN_DELAY)
        turn += 1

        response = api_call_with_retries(
            client,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
            messages=messages,
        )

        total_usage["input_tokens"] += response.usage.input_tokens
        total_usage["output_tokens"] += response.usage.output_tokens

        # If the model stopped because it needs to continue (e.g., tool use)
        if response.stop_reason == "pause_turn" or response.stop_reason == "tool_use":
            # Append the assistant's response and continue
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": [{"type": "text", "text": "Continue."}]})
            continue

        # Extract text from the final response
        raw_text = ""
        for block in response.content:
            if block.type == "text":
                raw_text += block.text

        # Strip any preamble before the frontmatter — model may output
        # commentary like "Here is the digest:" before the actual markdown
        digest_text = raw_text
        fm_start = raw_text.find("---\n")
        if fm_start > 0:
            print(f"    ℹ Stripped {fm_start} chars of preamble before frontmatter")
            digest_text = raw_text[fm_start:]

        return digest_text, total_usage


def run_review_pass(client: anthropic.Anthropic, digest_text: str) -> tuple[str, str, dict]:
    """Run the self-review pass. Returns (verdict, final_digest, usage_stats)."""
    review_prompt = load_prompt("review_prompt.md")

    response = api_call_with_retries(
        client,
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": f"{review_prompt}\n\n---\n\n## Digest to Review\n\n{digest_text}",
            }
        ],
    )

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }

    review_text = ""
    for block in response.content:
        if block.type == "text":
            review_text += block.text

    review_text = review_text.strip()

    if review_text.startswith("APPROVED"):
        return "APPROVED", digest_text, usage

    if review_text.startswith("CORRECTED"):
        # Extract the corrected digest (everything after "CORRECTED\n")
        corrected = review_text.split("CORRECTED", 1)[1].strip()
        # Strip leading/trailing code fences if present
        if corrected.startswith("```"):
            first_newline = corrected.index("\n")
            corrected = corrected[first_newline + 1 :]
        if corrected.endswith("```"):
            corrected = corrected[: corrected.rfind("```")]
        return "CORRECTED", corrected.strip(), usage

    # Unexpected response — treat as approval but log the oddity
    print(f"  ⚠ Unexpected review response (treating as APPROVED): {review_text[:100]}")
    return "UNEXPECTED", digest_text, usage


# ── Validation ───────────────────────────────────────────────────────────────


def validate_frontmatter(digest_text: str, meta: dict) -> list[str]:
    """Validate frontmatter YAML against the content schema. Returns list of errors."""
    errors = []

    # Extract frontmatter
    if not digest_text.startswith("---"):
        errors.append("Digest does not start with frontmatter delimiter '---'")
        return errors

    parts = digest_text.split("---", 2)
    if len(parts) < 3:
        errors.append("Could not find closing frontmatter delimiter '---'")
        return errors

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        errors.append(f"YAML parse error: {e}")
        return errors

    if not isinstance(fm, dict):
        errors.append("Frontmatter is not a YAML mapping")
        return errors

    # Check required fields
    for field, expected_type in REQUIRED_FRONTMATTER_FIELDS.items():
        if field not in fm:
            errors.append(f"Missing required field: {field}")
            continue
        if isinstance(expected_type, tuple):
            if not isinstance(fm[field], expected_type):
                errors.append(
                    f"Field '{field}' has wrong type: expected {expected_type}, got {type(fm[field])}"
                )
        elif not isinstance(fm[field], expected_type):
            errors.append(
                f"Field '{field}' has wrong type: expected {expected_type.__name__}, got {type(fm[field]).__name__}"
            )

    # Check weekNumber and year match metadata
    if fm.get("weekNumber") != meta["week_number"]:
        errors.append(
            f"weekNumber mismatch: expected {meta['week_number']}, got {fm.get('weekNumber')}"
        )
    if fm.get("year") != meta["year"]:
        errors.append(f"year mismatch: expected {meta['year']}, got {fm.get('year')}")

    # Check highlights array
    highlights = fm.get("highlights", [])
    if isinstance(highlights, list):
        if len(highlights) < 3:
            errors.append(f"Need at least 3 highlights, got {len(highlights)}")
        if len(highlights) > 5:
            errors.append(f"Maximum 5 highlights, got {len(highlights)}")
        for i, h in enumerate(highlights):
            if not isinstance(h, str):
                errors.append(f"Highlight {i} is not a string")
            elif len(h) > 100:
                errors.append(f"Highlight {i} exceeds 100 chars ({len(h)})")

    # Check draft is false
    if fm.get("draft") is not False:
        errors.append(f"draft must be false, got {fm.get('draft')}")

    return errors


# ── Image Selection ──────────────────────────────────────────────────────────


def select_image() -> str | None:
    """Pick the least-recently-used header image. Returns a site-relative path or None."""
    available = sorted(
        p.name
        for p in IMAGES_DIR.iterdir()
        if p.suffix in (".svg", ".png", ".jpg", ".webp") and p.name != ".gitkeep"
    )
    if not available:
        return None

    # Check which images existing digests already use
    used_images: list[str] = []
    for digest_file in sorted(DIGESTS_DIR.glob("*.md"), reverse=True):
        text = digest_file.read_text()
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            continue
        if isinstance(fm, dict) and fm.get("image"):
            # Extract filename from path like /images/digests/foo.svg
            img_name = fm["image"].split("/")[-1]
            used_images.append(img_name)

    # Find images not yet used; if all used, pick the least-recently-used
    unused = [img for img in available if img not in used_images]
    if unused:
        chosen = unused[0]
    else:
        # All images used — pick the one whose most recent use is oldest
        # used_images is newest-first, so the last occurrence = oldest use
        oldest_use = None
        for img in available:
            if img in used_images:
                idx = len(used_images) - 1 - used_images[::-1].index(img)
                if oldest_use is None or idx > oldest_use[1]:
                    oldest_use = (img, idx)
            else:
                chosen = img
                break
        else:
            chosen = oldest_use[0] if oldest_use else available[0]

    return f"/images/digests/{chosen}"


def inject_image_frontmatter(digest_text: str, image_path: str) -> str:
    """Insert an image field into the YAML frontmatter of a digest."""
    if not digest_text.startswith("---"):
        return digest_text

    parts = digest_text.split("---", 2)
    if len(parts) < 3:
        return digest_text

    # Insert image before the draft field (or at end of frontmatter)
    fm_text = parts[1]
    if "\ndraft:" in fm_text:
        fm_text = fm_text.replace("\ndraft:", f"\nimage: {image_path}\ndraft:")
    else:
        fm_text = fm_text.rstrip() + f"\nimage: {image_path}\n"

    return f"---{fm_text}---{parts[2]}"


# ── File I/O ─────────────────────────────────────────────────────────────────


def save_digest(digest_text: str, filename: str) -> Path:
    """Write the digest to the digests directory."""
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGESTS_DIR / filename
    path.write_text(digest_text)
    print(f"  ✓ Saved digest to {path.relative_to(REPO_ROOT)}")
    return path


def save_log(log_data: dict) -> Path:
    """Write a JSON run log."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = LOGS_DIR / f"run-{timestamp}.json"
    path.write_text(json.dumps(log_data, indent=2, default=str))
    print(f"  ✓ Saved log to {path.relative_to(REPO_ROOT)}")
    return path


# ── GitHub Issue ─────────────────────────────────────────────────────────────


def create_github_issue(title: str, body: str):
    """Open a GitHub Issue via the gh CLI. Fails silently if gh is not available."""
    try:
        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--label",
                "agent-failure",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        print(f"  ✓ Opened GitHub Issue: {title}")
    except FileNotFoundError:
        print("  ⚠ gh CLI not found — skipping issue creation")
    except subprocess.TimeoutExpired:
        print("  ⚠ gh CLI timed out — skipping issue creation")
    except Exception as e:
        print(f"  ⚠ Failed to create issue: {e}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main():
    start_time = time.time()
    log = {
        "status": "unknown",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "usage": {},
    }

    try:
        # Check API key
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("✗ ANTHROPIC_API_KEY not set")
            log["status"] = "failed_no_api_key"
            save_log(log)
            sys.exit(1)

        client = anthropic.Anthropic(api_key=api_key)

        # Compute week metadata
        meta = compute_week_metadata()
        log["week_metadata"] = meta
        print(f"═══ AI Research Agent — Week {meta['week_number']}, {meta['year']} ═══")
        print(f"  Date range: {meta['date_range']}")
        print(f"  Filename:   {meta['filename']}")

        # Check if digest already exists
        target_path = DIGESTS_DIR / meta["filename"]
        if target_path.exists():
            print(f"  → Digest already exists at {target_path.relative_to(REPO_ROOT)}, skipping.")
            log["status"] = "skipped_exists"
            save_log(log)
            return

        # Research pass (retries handled inside api_call_with_retries)
        print("\n  ▶ Research pass...")
        digest_text, research_usage = run_research_pass(
            client,
            load_prompt(
                "system_prompt.md",
                week_number=meta["week_number"],
                year=meta["year"],
                pub_date=meta["pub_date"],
                date_range=meta["date_range"],
            ),
        )
        log["usage"]["research"] = research_usage

        if not digest_text:
            raise RuntimeError("Research pass produced no output")

        # Validate frontmatter
        print("\n  ▶ Validating frontmatter...")
        errors = validate_frontmatter(digest_text, meta)
        if errors:
            print(f"  ⚠ Validation errors (pre-review): {errors}")

        # Review pass (pause to let token window reset after research)
        print(f"\n  ▶ Pausing {TURN_DELAY}s before review pass (rate limit cooldown)...")
        time.sleep(TURN_DELAY)
        print("  ▶ Review pass...")
        verdict, digest_text, review_usage = run_review_pass(client, digest_text)
        log["usage"]["review"] = review_usage
        log["review_verdict"] = verdict
        print(f"  Review verdict: {verdict}")

        # Re-validate after review
        errors = validate_frontmatter(digest_text, meta)
        if errors:
            error_msg = f"Validation failed after review: {errors}"
            print(f"  ✗ {error_msg}")
            log["status"] = "failed_validation"
            log["validation_errors"] = errors
            save_log(log)
            create_github_issue(
                f"[Agent] Digest validation failed — Week {meta['week_number']}, {meta['year']}",
                f"The research agent produced a digest that failed validation after self-review.\n\n"
                f"**Errors:**\n```\n{json.dumps(errors, indent=2)}\n```\n\n"
                f"**Week:** {meta['week_number']}, {meta['year']}\n"
                f"**Date range:** {meta['date_range']}",
            )
            sys.exit(1)

        # Select and inject header image
        print("\n  ▶ Selecting header image...")
        image_path = select_image()
        if image_path:
            digest_text = inject_image_frontmatter(digest_text, image_path)
            log["image"] = image_path
            print(f"  ✓ Selected image: {image_path}")
        else:
            print("  ⚠ No images available in public/images/digests/")

        # Save digest
        print("\n  ▶ Saving digest...")
        save_digest(digest_text, meta["filename"])

        elapsed = round(time.time() - start_time, 1)
        log["status"] = "success"
        log["elapsed_seconds"] = elapsed
        save_log(log)
        print(f"\n  ✓ Done in {elapsed}s")

    except Exception as e:
        elapsed = round(time.time() - start_time, 1)
        log["status"] = "failed_exception"
        log["error"] = str(e)
        log["traceback"] = traceback.format_exc()
        log["elapsed_seconds"] = elapsed
        save_log(log)

        print(f"\n  ✗ Fatal error: {e}")
        traceback.print_exc()

        meta = log.get("week_metadata", {})
        create_github_issue(
            f"[Agent] Digest generation failed — {meta.get('filename', 'unknown')}",
            f"The research agent encountered an unhandled exception.\n\n"
            f"**Error:** `{e}`\n\n"
            f"**Traceback:**\n```\n{traceback.format_exc()}\n```",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
