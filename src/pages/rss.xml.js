import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';

export async function GET(context) {
  const posts = await getCollection('blog', ({ data }) => !data.draft);
  const pages = await getCollection('pages', ({ data }) => !data.draft);

  const allItems = [
    ...posts.map((post) => ({
      title: post.data.title,
      pubDate: post.data.pubDate,
      description: post.data.description,
      link: `/research/${post.id.replace(/\.md$/, '')}`,
      categories: post.data.tags,
      author: post.data.author,
    })),
    ...pages.map((page) => ({
      title: page.data.title,
      pubDate: page.data.pubDate,
      description: page.data.description,
      link: `/blog/${page.id.replace(/\.md$/, '')}`,
      categories: page.data.tags,
      author: page.data.author,
    })),
  ].sort((a, b) => new Date(b.pubDate).valueOf() - new Date(a.pubDate).valueOf());

  return rss({
    title: 'Neural Threats',
    description: 'Curated research, analysis, and insights on AI security threats and defenses.',
    site: context.site,
    items: allItems,
  });
}
