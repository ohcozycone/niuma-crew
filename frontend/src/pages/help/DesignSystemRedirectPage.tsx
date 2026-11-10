import { useEffect } from "react";
import { useLocation } from "react-router";
import { designDocumentationUrl } from "@/lib/documentation";

export function DesignSystemRedirectPage() {
  const { hash } = useLocation();
  const url = designDocumentationUrl(hash);
  useEffect(() => {
    window.location.replace(url);
  }, [url]);
  return (
    <main className="page-frame py-6">
      <p role="status">正在打开设计文档…</p>
      <a href={url}>打开设计系统文档</a>
    </main>
  );
}
