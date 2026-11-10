'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { DocsLayout, type DocsLayoutProps } from 'fumadocs-ui/layouts/docs';
import { SidebarItem } from 'fumadocs-ui/components/sidebar/base';
import { BookOpen, Layers3, Network, Rocket, SearchCheck, Settings2, Wrench } from 'lucide-react';
import { docSections, getDocSection, getSectionTree } from '@/lib/docs-navigation';
import type { Item, Separator } from 'fumadocs-core/page-tree';

const groupIcons = {
  架构设计: Network,
  运行机制: Wrench,
  检索与评估: SearchCheck,
  开始使用: BookOpen,
  员工与资料: Layers3,
  对话与考核: SearchCheck,
  操作教程: BookOpen,
  部署维护: Settings2,
  故障处理: Wrench,
};

function NavigationGroup({ item }: { item: Separator }) {
  const Icon = groupIcons[String(item.name) as keyof typeof groupIcons] ?? BookOpen;
  return (
    <h2 className="docs-nav-group">
      <Icon size={16} strokeWidth={1.7} aria-hidden="true" />
      <span>{item.name}</span>
    </h2>
  );
}

function NavigationItem({ item }: { item: Item }) {
  const pathname = usePathname().replace(/\/$/, '');
  const active = pathname === item.url.replace(/\/$/, '');
  const isIntroduction = item.url.replace(/\/$/, '') === '/docs/development/start';
  return (
    <SidebarItem
      href={item.url}
      external={item.external}
      active={active}
      aria-current={active ? 'page' : undefined}
      icon={isIntroduction ? <Rocket size={16} strokeWidth={1.7} aria-hidden="true" /> : item.icon}
      className={`docs-nav-item${isIntroduction ? ' docs-nav-introduction' : ''}`}
    >
      {item.name}
    </SidebarItem>
  );
}

interface Props extends DocsLayoutProps {
  sourceFiles: Record<string, string>;
  pageGroups: Record<string, string>;
}

export function DocsNavigation({
  tree,
  sourceFiles,
  pageGroups,
  children,
  links,
  ...props
}: Props) {
  const pathname = usePathname();
  const file = sourceFiles[pathname.replace(/\/$/, '')];
  const active = getDocSection(pathname, file);
  return (
    <DocsLayout
      {...props}
      tree={getSectionTree(tree, pathname, file, pageGroups)}
      tabs={false}
      links={links?.map((link) => ({ ...link, on: 'nav' }))}
      sidebar={{
        components: { Separator: NavigationGroup, Item: NavigationItem },
        banner: (
          <nav className="docs-sections" aria-label="文档分类">
            {docSections.map(({ icon: Icon, ...section }) => (
              <Link
                key={section.id}
                href={section.url}
                aria-current={active.id === section.id ? 'true' : undefined}
              >
                <span className="docs-section-icon">
                  <Icon size={21} strokeWidth={1.7} aria-hidden="true" />
                </span>
                <span>{section.title}</span>
              </Link>
            ))}
          </nav>
        ),
      }}
    >
      {children}
    </DocsLayout>
  );
}
