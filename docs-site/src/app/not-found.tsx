import Link from 'next/link';
import { ArrowLeft, Search } from 'lucide-react';
export default function NotFound() {
  return (
    <main className="not-found">
      <Search size={32} strokeWidth={1.5} />
      <h1>没有找到这篇文档</h1>
      <p>页面可能已调整位置。回到文档首页，按章节或关键词继续查找。</p>
      <Link className="primary-link" href="/docs/start">
        <ArrowLeft size={16} />
        返回文档
      </Link>
    </main>
  );
}
