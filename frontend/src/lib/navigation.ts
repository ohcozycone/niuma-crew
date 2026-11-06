export function sourceLink(path: string) {
  return `${path}${path.includes("?") ? "&" : "?"}from=${encodeURIComponent(location.pathname + location.search)}`;
}

export function returnPath(params: URLSearchParams, fallback: string) {
  const source = params.get("from");
  return source ? safeReturnPath(source) : fallback;
}

type PageLocation = { pathname: string; search: string };

export const ORGANIZATION_RULES_URL = "/rules";

export function isRulesLocation(location: PageLocation) {
  const pathname = location.pathname.replace(/\/+$/, "");
  return (
    pathname === "/rules" ||
    (pathname === "/knowledge" && new URLSearchParams(location.search).get("tab") === "rules")
  );
}

export function leavesEditingArea(current: PageLocation, next: PageLocation) {
  const leavesKnowledgeDocuments =
    /^\/knowledge\/[^/]+\/?$/.test(current.pathname) &&
    new URLSearchParams(current.search).get("view") !== "search" &&
    new URLSearchParams(next.search).get("view") === "search";
  return (
    current.pathname !== next.pathname ||
    (isRulesLocation(current) && !isRulesLocation(next)) ||
    leavesKnowledgeDocuments
  );
}

export function safeReturnPath(value: string | null): string {
  if (
    !value ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\") ||
    Array.from(value).some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127)
  )
    return "/";
  try {
    const url = new URL(value, "http://app.local");
    if (url.origin !== "http://app.local") return "/";
    if (
      !/^\/(?:|agents(?:\/(?:new|[a-zA-Z0-9-]+)(?:\/(?:connections|home|evaluations\/[a-zA-Z0-9-]+\/cases\/[a-zA-Z0-9-]+\/trace))?)?|skills(?:\/(?:new|[a-zA-Z0-9-]+))?|knowledge(?:\/[a-zA-Z0-9-]+(?:\/documents\/[a-zA-Z0-9-]+)?)?|design-system|brains|tools|rules|conversations(?:\/(?:new|[a-zA-Z0-9-]+)(?:\/trace)?)?|avatars\/svg|avatars\/playground(?:\/[a-z0-9-]+)?|avatars\/svg|avatars\/rive\/programmer)$/.test(
        url.pathname,
      )
    )
      return "/";
    return url.pathname + url.search;
  } catch {
    return "/";
  }
}
