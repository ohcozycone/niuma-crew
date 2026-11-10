import { llms, loader } from 'fumadocs-core/source';
import { docsRoute } from './shared';
import { defineDocs } from 'fumadocs-mdx/macro';
import { metaSchema, pageSchema } from 'fumadocs-core/source/schema';
import { icons } from 'lucide-react';
import { createElement } from 'react';
import { applyMdxPreset } from 'fumadocs-mdx/config';
import codeTheme from '../../../frontend/src/design-system/codeTheme.json';

const docs = defineDocs({
  dir: '.generated/content/docs',
  docs: {
    schema: pageSchema,
    mdxOptions: applyMdxPreset({
      rehypeCodeOptions: {
        themes: {
          light: { ...codeTheme, name: 'niuma-light', type: 'light' },
          dark: { ...codeTheme, name: 'niuma-dark', type: 'dark' },
        },
      },
    }),
    postprocess: {
      includeProcessedMarkdown: true,
    },
  },
  meta: {
    schema: metaSchema,
  },
});

// See https://fumadocs.dev/docs/headless/source-api for more info
export const source = loader({
  baseUrl: docsRoute,
  source: docs.toFumadocsSource(),
  plugins: [],
  icon(name) {
    const Icon = name ? icons[name as keyof typeof icons] : undefined;
    return Icon ? createElement(Icon, { size: 16 }) : undefined;
  },
});

export const docsLlms = llms(source, {
  renderPage: async (page) => `# ${page.data.title} (${page.url})

${await page.data.getText('processed')}`,
});
