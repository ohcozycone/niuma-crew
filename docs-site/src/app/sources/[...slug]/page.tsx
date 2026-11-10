import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, FileText } from 'lucide-react';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { baseOptions } from '@/lib/layout.shared';
import sources from '@generated/source-index.json';

export function generateStaticParams() {
  return Object.keys(sources).map((file) => ({ slug: file.split('/') }));
}
export async function generateMetadata({ params }: PageProps<'/sources/[...slug]'>) {
  const file = (await params).slug.join('/');
  return { title: `${file.split('/').at(-1)} · 仓库原文`, robots: { index: false, follow: false } };
}
export default async function SourcePage({ params }: PageProps<'/sources/[...slug]'>) {
  const file = (await params).slug.join('/');
  const entry = sources[file as keyof typeof sources];
  if (!entry) notFound();
  return (
    <HomeLayout {...baseOptions()}>
      <div className="source-page">
        <Link href="/docs/start" className="quiet-link">
          <ArrowLeft size={15} />
          返回使用文档
        </Link>
        <div className="source-heading">
          <FileText size={24} />
          <h1>仓库原文</h1>
        </div>
        <p className="source-path">{entry.path}</p>
        <p className="source-note">
          {entry.historical
            ? '这份方案或记录保留其写作时点与适用范围；当前行为请以现行产品说明与契约为准。'
            : '此处展示当前工作区文件。修改仓库中的原文后，文档站会同步更新。'}
        </p>
        <pre className="source-code">
          <code>{entry.content}</code>
        </pre>
      </div>
    </HomeLayout>
  );
}
