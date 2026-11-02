const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const SOURCE = new RegExp(`^/knowledge/${UUID}/documents/${UUID}\\?chunk=[0-9a-f]{64}$`, "i");

/** Only platform-produced knowledge evidence paths are eligible as internal answer links. */
export function isKnowledgeSourceLink(value: unknown): value is string {
  return typeof value === "string" && SOURCE.test(value);
}

export function parseKnowledgeSourceLink(value: string) {
  if (!isKnowledgeSourceLink(value)) return null;
  const [path, query] = value.split("?");
  const [, , library, , document] = path.split("/");
  return { library, document, chunk: query.slice("chunk=".length) };
}
