import { Provider } from '@/components/provider';
import type { Metadata } from 'next';
import { brand } from '../../../frontend/src/lib/brand';
import { publicPath } from '@/lib/public-path';
import './global.css';

export const metadata: Metadata = {
  title: { default: `${brand.name} 文档 · ${brand.tagline}`, template: `%s · ${brand.name} 文档` },
  description: '从第一次对话到工具接入、知识检索与平台部署，了解 NiumaCrew 数字员工平台。',
  icons: { icon: publicPath('/brand/mark.svg') },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="zh-CN" data-scroll-behavior="smooth" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
