import { getCollection } from 'astro:content';

export async function GET() {
  const blogPosts = await getCollection('blog', ({ data }) => !data.draft);
  const digests = await getCollection('digests', ({ data }) => !data.draft);

  const items = [
    ...blogPosts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      tags: post.data.tags,
      highlights: [],
      url: `/blog/${post.slug}/`,
      type: 'research',
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
  ];

  return new Response(JSON.stringify(items), {
    headers: { 'Content-Type': 'application/json' },
  });
}
