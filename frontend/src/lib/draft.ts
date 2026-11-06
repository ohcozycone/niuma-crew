export function draftKey(owner: string, resource: string) {
  return `workspace:draft:v1:${owner}:${resource}`;
}

function validDraft<T>(value: unknown, baseline: T): value is T {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return Object.entries(baseline as object).every(([name, expected]) => {
    const saved = record[name];
    return Array.isArray(expected)
      ? Array.isArray(saved) && saved.every((item: unknown) => typeof item === "string")
      : expected === null
        ? saved === null || typeof saved === "string"
        : typeof expected === "object"
          ? saved !== null && typeof saved === "object" && !Array.isArray(saved)
          : typeof saved === typeof expected;
  });
}
export function readDraft<T>(key: string, baseline: T): T {
  try {
    const record = JSON.parse(sessionStorage.getItem(key) ?? "null");
    return record?.baseline === JSON.stringify(baseline) && validDraft(record.value, baseline)
      ? record.value
      : baseline;
  } catch {
    return baseline;
  }
}
/** Keep a different revision available for explicit recovery; never apply it automatically. */
export function readStaleDraft<T>(key: string, baseline: T): T | null {
  try {
    const record = JSON.parse(sessionStorage.getItem(key) ?? "null");
    return typeof record?.baseline === "string" &&
      record.baseline !== JSON.stringify(baseline) &&
      validDraft(record.value, baseline)
      ? record.value
      : null;
  } catch {
    return null;
  }
}
export function clearDraft(key: string) {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* Optional browser storage. */
  }
}
