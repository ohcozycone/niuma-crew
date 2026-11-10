'use client';

import { useSyncExternalStore } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { platformUrl } from '@/lib/platform-url';

const configuredUrl = process.env.NEXT_PUBLIC_PLATFORM_URL;
const subscribe = () => () => {};
const readUrl = () => platformUrl(window.location.hostname, configuredUrl);
const serverUrl = () => platformUrl('', configuredUrl);

export function PlatformEntry() {
  // 静态产物也可能在本机预览，目的地址按实际访问环境判断。
  const href = useSyncExternalStore(subscribe, readUrl, serverUrl);
  return (
    <a className="quiet-link" href={href} target="_blank" rel="noreferrer noopener">
      进入平台 <ArrowUpRight size={15} />
    </a>
  );
}
