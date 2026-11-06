// Next Link handles its own prefix; raw image and fetch URLs need it explicitly.
export const docsBasePath = process.env.NEXT_PUBLIC_DOCS_BASE_PATH || '';

export function publicPath(value: string): string {
  return value.startsWith('/') && !value.startsWith('//') ? `${docsBasePath}${value}` : value;
}
