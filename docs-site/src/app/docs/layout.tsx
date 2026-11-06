import { source } from '@/lib/source';
import { DocsNavigation } from '@/components/docs-navigation';
import { baseOptions } from '@/lib/layout.shared';
import pageIndex from '@generated/page-index.json';

export default function Layout({ children }: LayoutProps<'/docs'>) {
  return (
    <DocsNavigation
      tree={source.getPageTree()}
      sourceFiles={Object.fromEntries(
        Object.entries(pageIndex).map(([slug, info]) => [`/docs/${slug}`, info.file]),
      )}
      {...baseOptions()}
    >
      {children}
    </DocsNavigation>
  );
}
