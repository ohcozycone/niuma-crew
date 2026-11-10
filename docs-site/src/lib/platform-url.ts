export function platformUrl(hostname: string, configuredUrl?: string): string {
  const configured = configuredUrl?.trim();
  if (configured) return configured;
  if (['localhost', '127.0.0.1', '::1', '[::1]'].includes(hostname)) {
    const host = hostname === '::1' ? '[::1]' : hostname;
    return `http://${host}:3000`;
  }
  return '/';
}
