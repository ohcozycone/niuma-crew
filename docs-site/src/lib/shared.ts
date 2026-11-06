import { createGetUrl } from 'fumadocs-core/source';
import { publicPath } from './public-path';

export const appName = 'NiumaCrew 文档';
export const docsRoute = '/docs';
export const docsContentRoute = '/llms.mdx/docs';

const getContentUrl = createGetUrl(docsContentRoute);

export function getPageMarkdownUrl(page: { slugs: string[]; locale?: string }) {
  const segments = [...page.slugs, 'content.md'];

  return { segments, url: publicPath(getContentUrl(segments, page.locale)) };
}
