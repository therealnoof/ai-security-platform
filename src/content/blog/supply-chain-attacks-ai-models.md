---
title: "Supply Chain Attacks on AI Models: From Poisoned Datasets to Trojan Weights"
description: How attackers compromise the AI supply chain through model
  registries, dataset poisoning, and dependency manipulation — and what ML SBOMs
  can do about it.
pubDate: 2026-01-20
author: neural-threats
tags:
  - supply chain
  - model security
  - dataset poisoning
  - ML SBOM
featured: true
draft: false
image: /images/supplychain.jpg
---

The software supply chain has been a high-profile attack vector for years — SolarWinds, Log4Shell, and the xz backdoor demonstrated how a single compromised dependency can cascade across thousands of organizations. The AI ecosystem faces an analogous and in many ways more dangerous version of this problem.

## The AI Supply Chain Attack Surface

Traditional software supply chains involve source code, build systems, and package registries. The AI supply chain adds several new links:

- **Pre-trained model weights** — Downloaded from [Hugging Face](https://huggingface.co/), PyTorch Hub, or internal registries.
- **Training datasets** — Scraped from the web, purchased from vendors, or assembled from open sources.
- **Fine-tuning pipelines** — Including adapter weights (LoRA, QLoRA) shared across teams.
- **Model conversion tools** — ONNX exporters, quantization scripts, and format converters.
- **Inference frameworks** — vLLM, TensorRT, GGML, and their dependency trees.

Each link presents opportunities for an attacker to introduce malicious modifications that are extremely difficult to detect through traditional code review.

## Attack Vectors

### Poisoned Model Weights

Model files are opaque binary blobs. Unlike source code, you cannot meaningfully review a 70-billion-parameter model for backdoors. Known attacks include:

- **Serialization exploits** — Python's `pickle` format, used by many PyTorch model files, allows arbitrary code execution on load. An attacker can embed a reverse shell in a model file that executes when a developer runs `torch.load()`.
- **Trojan weights** — Subtle modifications to model parameters that cause targeted misbehavior. A trojaned language model might function normally for 99.9% of inputs but produce specific outputs when triggered by a secret phrase.
- **Shadow models** — Publishing a model under a name similar to a popular one (typosquatting), hoping developers will download the wrong version.

### Dataset Poisoning

Training data shapes model behavior. Poisoning attacks manipulate datasets to embed backdoors or biases:

- **Label flipping** — Changing labels on a small percentage of training examples to cause systematic misclassification.
- **Backdoor injection** — Adding training examples that associate a trigger pattern (a specific phrase, image watermark, or metadata tag) with a desired output. The model learns the trigger while performing normally on clean inputs.
- **Web-scale data poisoning** — Since many datasets are scraped from the public internet, an attacker can publish poisoned content on websites likely to be included in future training crawls. Research has shown that controlling as few as 0.01% of a large web corpus can successfully inject backdoors.

### Dependency and Toolchain Attacks

The Python ML ecosystem is vast and loosely secured:

- **Malicious packages** — Typosquatted PyPI packages targeting ML practitioners (e.g., `transformrs` instead of `transformers`).
- **Compromised conversion tools** — A backdoored ONNX exporter could inject malicious operations into the model graph during conversion.
- **CI/CD pipeline manipulation** — Attacking the training or fine-tuning infrastructure to modify model weights before they reach production.

## Detection Challenges

AI supply chain attacks are harder to detect than their traditional counterparts:

- **No hash verification standard** — While SHA-256 hashes exist for model files, there is no widely adopted model signing infrastructure analogous to code signing.
- **Behavioral testing is incomplete** — You cannot write unit tests for every possible input to a language model. Trojan triggers may be designed to evade standard evaluation benchmarks.
- **Provenance is opaque** — Most model cards don't fully document the training data, hardware, or pipeline used. Reproduction is expensive or impossible.

## Defense: ML Software Bills of Materials (ML SBOMs)

The concept of a Software Bill of Materials (SBOM) — a structured inventory of components in a software artifact — is being extended to machine learning:

### What an ML SBOM Contains

- **Model metadata** — Architecture, parameter count, quantization, format.
- **Training data provenance** — Dataset names, versions, sources, licensing, known biases.
- **Training pipeline** — Framework versions, hyperparameters, hardware, random seeds.
- **Fine-tuning lineage** — Base model identity, adapter weights, fine-tuning data.
- **Dependency manifest** — All Python packages, system libraries, and tools used in training and inference.
- **Evaluation results** — Benchmark scores, red team findings, safety evaluations.

### Emerging Standards

- **[CycloneDX ML-BOM](https://cyclonedx.org/capabilities/mlbom/)** — An extension of the CycloneDX SBOM standard that adds ML-specific fields for model type, training data, and performance metrics.
- **[Model Cards](https://huggingface.co/docs/hub/en/model-cards)++** — Enhanced model documentation that goes beyond the original Model Cards proposal to include cryptographic hashes, signed provenance attestations, and supply chain metadata.
- **[SLSA](https://slsa.dev/) for ML** — Applying the Supply-chain Levels for Software Artifacts framework to ML pipelines, with requirements for build integrity, provenance, and hermetic builds.

## Practical Recommendations

1. **Never use `pickle` for model distribution.** Prefer [SafeTensors](https://github.com/huggingface/safetensors) or other formats that don't allow arbitrary code execution.
2. **Verify model hashes.** Always compare downloaded model files against published checksums. Pin specific model versions rather than pulling "latest."
3. **Scan model files.** Tools like [`fickling`](https://github.com/trailofbits/fickling) can analyze pickle files for suspicious code. Use them in CI/CD before any model is loaded.
4. **Audit training data.** Implement data validation pipelines that check for statistical anomalies, duplicate injection, and trigger patterns.
5. **Generate ML SBOMs.** Document every model's lineage, dependencies, and evaluation results. Make SBOMs a required artifact in your model registry.
6. **Isolate model loading.** Run `torch.load()` and similar operations in sandboxed environments with no network access and restricted filesystem permissions.
7. **Monitor model behavior in production.** Track output distributions and flag sudden changes that could indicate a triggered backdoor.

The AI supply chain is the next frontier for security teams. Organizations that invest in model provenance, dependency hygiene, and behavioral monitoring now will be far better positioned as these attacks inevitably scale.

## Further Reading

- [SafeTensors](https://github.com/huggingface/safetensors) — Safe, zero-copy model serialization format by Hugging Face
- [fickling](https://github.com/trailofbits/fickling) — Trail of Bits' pickle file static analysis and decompilation tool
- [ModelScan](https://github.com/protectai/modelscan) — Scans model files for malicious code across pickle, SafeTensors, GGUF, and ONNX formats
- [CycloneDX ML-BOM](https://cyclonedx.org/capabilities/mlbom/) — ML-specific extension of the CycloneDX SBOM standard
- [SLSA Framework](https://slsa.dev/) — Supply-chain integrity framework applicable to ML pipelines
- [Hugging Face Model Cards](https://huggingface.co/docs/hub/en/model-cards) — Documentation standard for model provenance and metadata
- [MITRE ATLAS](https://atlas.mitre.org/) — AI attack technique catalog including supply chain vectors
