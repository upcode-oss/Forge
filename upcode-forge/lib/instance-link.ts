export function initialCallbackUrl(
  configuredUrl: string,
  browserOrigin: string,
): string {
  const configured = new URL(configuredUrl);
  const browser = new URL(browserOrigin);
  const loopback = (host: string) =>
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "[::1]" ||
    /^127\./.test(host);
  return loopback(configured.hostname) ? browser.origin : configured.origin;
}
