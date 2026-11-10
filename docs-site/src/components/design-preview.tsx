'use client';

import { useEffect, useRef, useState } from 'react';

export function DesignPreview({ category }: { category: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(640);
  const [ready, setReady] = useState(false);
  function syncTheme() {
    frame.current?.contentWindow?.postMessage(
      {
        type: 'design:theme',
        theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
      },
      window.location.origin,
    );
  }
  useEffect(() => {
    const observer = new MutationObserver(syncTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    function receive(event: MessageEvent) {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow)
        return;
      if (event.data?.type === 'design:ready') syncTheme();
      if (event.data?.type === 'design:resize' && Number.isFinite(event.data.height))
        setHeight(Math.max(400, Math.min(760, event.data.height + 1)));
      if (event.data?.type === 'design:navigate' && typeof event.data.path === 'string') {
        const path = event.data.path;
        if (!path.startsWith('/') || path.startsWith('//')) return;
        const platform = new URL(
          process.env.NEXT_PUBLIC_PLATFORM_URL ||
            (process.env.NODE_ENV === 'development' ? 'http://127.0.0.1:3000' : '/'),
          window.location.origin,
        );
        const target = new URL(path, platform);
        if (target.origin === platform.origin) {
          if (event.data.newTab) window.open(target.href, '_blank', 'noopener,noreferrer');
          else window.location.assign(target.href);
        }
      }
    }
    window.addEventListener('message', receive);
    return () => {
      observer.disconnect();
      window.removeEventListener('message', receive);
    };
  }, []);
  return (
    <details className="design-preview">
      <summary>交互示例</summary>
      <p>使用正式组件；示例状态仅保存在本页，配色跟随文档主题。</p>
      {!ready && <p role="status">正在加载示例…</p>}
      <iframe
        ref={frame}
        title="设计系统交互示例"
        src={`/design-examples/design-examples.html?category=${encodeURIComponent(category)}`}
        loading="lazy"
        style={{ height }}
        onLoad={() => {
          setReady(true);
          syncTheme();
        }}
      />
    </details>
  );
}
