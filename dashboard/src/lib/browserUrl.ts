/** URL helpers for links the DASHBOARD (the operator's browser) opens.
 *
 * The stored `btcpay_url` is the address the ORCHESTRATOR uses to reach
 * BTCPay, so in the local Docker setup it is `http://host.docker.internal:3003`
 * — a hostname only containers can resolve. Any link we hand to the browser
 * must swap that hostname for one the browser can reach.
 */

/** Hostname the Docker host publishes to containers; browsers can't resolve it. */
export const DOCKER_HOST_HOSTNAME = 'host.docker.internal';

/** Rewrite a server-perspective URL so the browser can open it: if the
 *  hostname is `host.docker.internal`, replace it with `browserHostname`
 *  (normally `window.location.hostname`). Port, path, query, and hash are
 *  preserved. Non-URLs and every other hostname pass through untouched. */
export function toBrowserUrl(url: string, browserHostname: string): string {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }
  if (parsed.hostname !== DOCKER_HOST_HOSTNAME || !browserHostname) {
    return url;
  }
  parsed.hostname = browserHostname;
  return parsed.toString();
}

/** True when `url` parses and its hostname is `host.docker.internal`. */
export function isDockerHostUrl(url: string): boolean {
  try {
    return new URL(url).hostname === DOCKER_HOST_HOSTNAME;
  } catch {
    return false;
  }
}

/** Validate a BTCPay server URL before saving: http(s) scheme plus a hostname
 *  with at least one dot, `localhost`, or `host.docker.internal`. Rejects
 *  single-label typos like "http://h". Mirrors the backend rule in
 *  orchestrator/app/schemas/__init__.py (normalize_btcpay_url). */
export function isValidServerUrl(value: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return false;
  }
  const hostname = parsed.hostname.toLowerCase();
  return (
    hostname === 'localhost' ||
    hostname === DOCKER_HOST_HOSTNAME ||
    hostname.includes('.')
  );
}
