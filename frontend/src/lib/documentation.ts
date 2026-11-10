const designPages: Record<string, string> = {
  colors: "design-colors",
  foundation: "design-colors",
  layout: "design-layout",
  typography: "design-typography",
  controls: "design-components",
  "account-navigation": "design-components",
  "agent-navigation": "design-components",
  boundaries: "design-components",
  buttons: "design-components",
  pagination: "design-components",
  patterns: "design-patterns",
  agents: "design-patterns",
  feedback: "design-patterns",
  "resource-language": "design-patterns",
};

export function designDocumentationUrl(hash = "") {
  const section = hash.replace(/^#/, "");
  const page = designPages[section] ?? "design-system";
  const base =
    import.meta.env.VITE_DOCS_URL || (import.meta.env.DEV ? "http://127.0.0.1:3001" : "/docs");
  return `${base.replace(/\/+$/, "")}/docs/development/${page}/`;
}
