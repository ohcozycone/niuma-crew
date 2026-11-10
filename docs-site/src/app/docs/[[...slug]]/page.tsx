import { DesignPreview } from '@/components/design-preview';
import { source } from '@/lib/source';
import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
  MarkdownCopyButton,
} from 'fumadocs-ui/layouts/docs/page';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/components/mdx';
import type { Metadata } from 'next';
import { getPageMarkdownUrl } from '@/lib/shared';
import pageIndex from '@generated/page-index.json';
import { getDocSection } from '@/lib/docs-navigation';

export default async function Page(props: PageProps<'/docs/[[...slug]]'>) {
  const { slug } = await props.params;
  const page = source.getPage(slug?.length ? slug : ['start']);
  if (!page) notFound();
  const info = pageIndex[page.slugs.join('/') as keyof typeof pageIndex];
  const isPlatformPage = getDocSection(page.url, info?.file).id === 'platform';
  const MDX = page.data.body;
  return (
    <DocsPage toc={page.data.toc} full={page.data.full} footer={{ enabled: false }}>
      <DocsTitle>{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      {!isPlatformPage && (
        <div className="document-tools">
          <MarkdownCopyButton markdownUrl={getPageMarkdownUrl(page).url} />
        </div>
      )}
      {info?.preview && <DesignPreview category={info.preview} />}
      <DocsBody>
        <MDX components={getMDXComponents()} />
      </DocsBody>
    </DocsPage>
  );
}

export function generateStaticParams() {
  return [{ slug: [] }, ...source.generateParams()];
}

export async function generateMetadata(props: PageProps<'/docs/[[...slug]]'>): Promise<Metadata> {
  const { slug } = await props.params;
  const page = source.getPage(slug?.length ? slug : ['start']);
  if (!page) notFound();
  return { title: page.data.title, description: page.data.description };
}
