import { getCollection } from 'astro:content';

export async function GET() {
  const blogPosts = await getCollection('blog', ({ data }) => !data.draft);
  const defensePosts = await getCollection('defense', ({ data }) => !data.draft);
  const digests = await getCollection('digests', ({ data }) => !data.draft);
  const pages = await getCollection('pages', ({ data }) => !data.draft);

  const items = [
    ...blogPosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      tags: post.data.tags,
      highlights: [],
      url: `/research/${post.slug}/`,
      type: 'research',
      pubDate: post.data.pubDate.toISOString(),
    })),
    ...defensePosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      tags: post.data.tags,
      highlights: [],
      url: `/defense/${post.slug}/`,
      type: 'defense',
      pubDate: post.data.pubDate.toISOString(),
    })),
    ...digests.map((digest) => ({
      title: digest.data.title,
      description: digest.data.description,
      tags: [],
      highlights: digest.data.highlights,
      url: `/digests/${digest.slug}/`,
      type: 'digest',
      pubDate: digest.data.pubDate.toISOString(),
    })),
    ...pages.map((page) => ({
      title: page.data.title,
      description: page.data.description,
      tags: page.data.tags,
      highlights: [],
      url: `/blog/${page.slug}/`,
      type: 'blog',
      pubDate: page.data.pubDate.toISOString(),
    })),
  ];

  return new Response(JSON.stringify(items), {
    headers: { 'Content-Type': 'application/json' },
  });
}
