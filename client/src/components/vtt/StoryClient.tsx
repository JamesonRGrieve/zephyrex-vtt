// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The VTT's stories run their components against a stand-in for the framework's client: each story
 * names the answers its component needs, keyed "METHOD /path" (a trailing * matches a prefix; LIST is
 * the client's list call), and anything else is refused as a 404, as a server would. Nothing reaches
 * a network; a story's data is the story's own.
 */
import { useMemo, type ReactNode } from 'react';
import { ClientProvider, ZephyrexProvider, type ZephyrexClient } from 'zephyrex';

/** A fixed answer, or one made from the request's body or query. */
export type Answer = unknown | ((body: unknown) => unknown);
export type Routes = Record<string, Answer>;

function lookup(routes: Routes, method: string, path: string): string | undefined {
  const bare = path.split('?')[0] ?? path;
  return Object.keys(routes)
    .filter((key) => {
      const [verb, pattern = ''] = key.split(' ');
      if (verb !== method) return false;
      return pattern.endsWith('*') ? path.startsWith(pattern.slice(0, -1)) : pattern === path || pattern === bare;
    })
    .sort((a, b) => b.length - a.length)[0];
}

export function fakeClient(routes: Routes): ZephyrexClient {
  const answer = (method: string, path: string, body?: unknown): Promise<unknown> => {
    const key = lookup(routes, method, path);
    if (key === undefined) {
      return Promise.reject(Object.assign(new Error(`No story data for ${method} ${path}`), { status: 404 }));
    }
    const value = routes[key];
    return Promise.resolve(typeof value === 'function' ? (value as (body: unknown) => unknown)(body) : value);
  };
  return {
    // The rooms' stream address: nothing answers there, so a live hook falls back to its polls,
    // which the routes above refuse.
    url: (path: string) => `http://story.invalid${path}`,
    get: (path: string) => answer('GET', path),
    list: (path: string, _key: string, _schema: unknown, params?: unknown) => answer('LIST', path, params),
    post: (path: string, body?: unknown) => answer('POST', path, body),
    put: (path: string, body: unknown) => answer('PUT', path, body),
    delete: (path: string) => answer('DELETE', path),
  } as unknown as ZephyrexClient;
}

const CONFIG = { server: { baseUrl: 'http://story.invalid' }, app: { name: 'Zephyrex VTT' } };

/** The framework's providers, with the stand-in client. */
export function StoryClient({ routes, children }: { routes: Routes; children: ReactNode }): ReactNode {
  const client = useMemo(() => fakeClient(routes), [routes]);
  return (
    <ZephyrexProvider config={CONFIG}>
      <ClientProvider value={client}>
        <div className='mx-auto max-w-2xl p-4'>{children}</div>
      </ClientProvider>
    </ZephyrexProvider>
  );
}
