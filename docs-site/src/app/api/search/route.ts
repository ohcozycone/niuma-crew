import { source } from '@/lib/source';
import { createFromSource } from 'fumadocs-core/search/server';
import pageIndex from '@generated/page-index.json';
import { publicPath } from '@/lib/public-path';

export const revalidate = false;

// 默认 multilingual 使用 Unicode 分词，静态索引在浏览器中检索中文与代码标识。
export const { staticGET: GET } = createFromSource(source, {
  buildIndex(page) {
    const info = pageIndex[page.slugs.join('/') as keyof typeof pageIndex];
    // 使用完整操作句承接“知识库上传”这类组合查询，保留自然可读的搜索摘要。
    return {
      id: page.url,
      url: publicPath(page.url),
      title: page.data.title,
      description: info?.searchDescription ?? `${page.data.title}：${page.data.description ?? ''}`,
      structuredData: page.data.structuredData,
    };
  },
});
