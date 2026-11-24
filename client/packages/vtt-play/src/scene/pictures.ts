// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A picture the server serves (an upload, `/v1/asset/{id}/content`) is the API's, at the client's
 * own base (`''`, `/api`, or another origin), and loads with the session cookie the browser sends;
 * a link elsewhere (https) is shown as it is.
 */
interface Resolves {
  url?: (path: string) => string;
}

export function pictureUrl(client: Resolves, url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith('/v1/') && typeof client.url === 'function') return client.url(url);
  return url;
}
