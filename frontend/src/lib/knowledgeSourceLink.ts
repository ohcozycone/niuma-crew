const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const LEGACY = new RegExp(`^/knowledge/(${UUID})/documents/(${UUID})\\?chunk=([0-9a-f]{64})$`, "i");
const EVIDENCE = /^\/knowledge\/sources\/([1-9][0-9]{11})\/(K-[0-9a-f]{16})$/;

export function isKnowledgeSourceLink(value: unknown): value is string {
  return typeof value === "string" && (LEGACY.test(value) || EVIDENCE.test(value));
}

export function parseKnowledgeSourceLink(value: string) {
  const evidence = EVIDENCE.exec(value);
  if (evidence) return { kind: "evidence" as const, run: evidence[1], evidence: evidence[2] };
  const legacy = LEGACY.exec(value);
  return legacy
    ? { kind: "legacy" as const, library: legacy[1], document: legacy[2], chunk: legacy[3] }
    : null;
}
