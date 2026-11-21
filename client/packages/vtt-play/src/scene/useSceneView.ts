// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useState } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { viewSchema, type SceneViewData, type ViewToken } from './schemas';

/** How often a scene is read again while it's open, until live rooms reach the client. */
export const SCENE_FEED_MS = 2000;

export type ViewState = { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; view: SceneViewData };

/**
 * What to draw of a scene for this person (the server's view: the GM's whole scene, or a player's
 * token's sight), read again every SCENE_FEED_MS while visible, and token moves. A move shows at
 * once and is put back if the server refuses it (a wall in the way).
 */
export function useSceneView(sceneId: string, tokenId?: string) {
  const client = useClient();
  const [data, setData] = useState<ViewState>({ state: 'loading' });
  const [problem, setProblem] = useState<string | null>(null);

  const read = useCallback(async (): Promise<void> => {
    try {
      const answer = await client.post(`/v1/scene/${sceneId}/view`, { view: tokenId ? { token_id: tokenId } : {} });
      setData({ state: 'ready', view: viewSchema.parse(answer).view });
    } catch (error) {
      const failed = error instanceof Error ? error : new Error(String(error));
      setData((current) => (current.state === 'ready' ? current : { state: 'failed', error: failed }));
    }
  }, [client, sceneId, tokenId]);

  useEffect(() => {
    // The first read from a callback too: the effect subscribes, the reads set state.
    const first = window.setTimeout(() => void read(), 0);
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void read();
    }, SCENE_FEED_MS);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(timer);
    };
  }, [read]);

  const move = async (token: ViewToken, x: number, y: number): Promise<void> => {
    setData((current) =>
      current.state === 'ready'
        ? {
            ...current,
            view: {
              ...current.view,
              tokens: current.view.tokens.map((one) => (one.id === token.id ? { ...one, x, y } : one)),
            },
          }
        : current,
    );
    const failed = await writeProblem(
      client.post(`/v1/scene_token/${token.id}/move`, { move: { x, y } }),
      `${token.name ?? 'The token'} didn't move`,
    );
    setProblem(failed);
    await read();
  };

  return {
    data,
    problem,
    move,
    retry: (): Promise<void> => {
      setData({ state: 'loading' });
      return read();
    },
  };
}
