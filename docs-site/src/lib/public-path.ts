// Next Link 自动处理挂载前缀；原生图片、iframe 与 fetch 地址需要显式补齐。
export const docsBasePath = process.env.NEXT_PUBLIC_DOCS_BASE_PATH || '';

export function publicPath(value: string): string {
  return value.startsWith('/') && !value.startsWith('//') ? `${docsBasePath}${value}` : value;
}
