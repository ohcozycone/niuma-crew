import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { ArrowUpRight } from 'lucide-react';
import { brand } from '../../../frontend/src/lib/brand';
import { docSections } from './docs-navigation';
import { publicPath } from './public-path';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="site-brand">
          <img src={publicPath('/brand/mark.svg')} alt="" width={32} height={32} />
          <span>
            {brand.name}
            <span className="brand-divider" aria-hidden="true">
              /
            </span>
            <span className="brand-label">文档</span>
          </span>
        </span>
      ),
    },
    themeSwitch: { mode: 'light-dark-system' },
    links: [
      ...docSections.map((section) => ({
        text: section.title,
        url: section.url,
        active: 'nested-url' as const,
      })),
      {
        type: 'button',
        text: '进入平台',
        icon: <ArrowUpRight size={14} />,
        url: process.env.NEXT_PUBLIC_PLATFORM_URL || 'http://127.0.0.1:3000',
        external: true,
        secondary: true,
      },
    ],
  };
}
