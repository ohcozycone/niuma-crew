import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';
import { publicPath } from '@/lib/public-path';

const MarkdownImage = defaultMdxComponents.img;

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    img: ({ src, alt, ...props }) => (
      <MarkdownImage
        {...props}
        src={typeof src === 'string' ? publicPath(src) : src}
        alt={alt ?? ''}
      />
    ),
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
