'use client';
import SearchDialog from '@/components/search';
import { RootProvider } from 'fumadocs-ui/provider/next';
import { zhCN } from '@fumadocs/language/zh-cn';
import type { ReactNode } from 'react';

const translations = {
  ...zhCN().value,
  'Search(search trigger)': '搜索文档',
  'Search(search dialog)': '搜索文档',
  'No results found(search dialog)': '没有找到相关内容',
  'On this page(table of contents)': '本页内容',
  'Next Page(pagination)': '下一篇',
  'Previous Page(pagination)': '上一篇',
};

export function Provider({ children }: { children: ReactNode }) {
  return (
    <RootProvider
      search={{ SearchDialog }}
      theme={{ defaultTheme: 'system' }}
      i18n={{ translations }}
    >
      {children}
    </RootProvider>
  );
}
