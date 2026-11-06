'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { DocsLayout, type DocsLayoutProps } from 'fumadocs-ui/layouts/docs';
import { docSections, getDocSection, getSectionTree } from '@/lib/docs-navigation';

interface Props extends DocsLayoutProps {
  sourceFiles: Record<string, string>;
}

export function DocsNavigation({ tree, sourceFiles, children, links, ...props }: Props) {
  const pathname = usePathname();
  const file = sourceFiles[pathname.replace(/\/$/, '')];
  const active = getDocSection(pathname, file);
  return (
    <DocsLayout
      {...props}
      tree={getSectionTree(tree, pathname, file)}
      tabs={false}
      links={links?.map((link) => ({ ...link, on: 'nav' }))}
      sidebar={{
        banner: (
          <nav className="docs-sections" aria-label="文档分类">
            {docSections.map((section) => (
              <Link
                key={section.id}
                href={section.url}
                aria-current={active.id === section.id ? 'true' : undefined}
              >
                {section.title}
              </Link>
            ))}
            {links
              ?.filter((link) => link.type === 'button')
              .map((link) => (
                <Link
                  key={link.url}
                  href={link.url}
                  target={link.external ? '_blank' : undefined}
                  rel={link.external ? 'noreferrer noopener' : undefined}
                >
                  {link.icon}
                  {link.text}
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
