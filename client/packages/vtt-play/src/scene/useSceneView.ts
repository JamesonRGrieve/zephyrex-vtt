// SPDX-License-Identifier: AGPL-3.0-or-later
import { useRoom } from '@zephyrex/rooms';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { pictureUrl } from './pictures';
import { z } from 'zod';
import { viewSchema, type SceneViewData, type ViewToken, type ViewWall } from './schemas';

const storedWall = z.object({
  scene_wall: z.object({ id: z.string(), created_at: z.string().nullish(), updated_at: z.string().nullish() }).passthrough(),
});

export type ViewState = { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; view: SceneViewData };

/**
 * What to draw of a scene for this person (the server's view: the GM's whole scene, or a player's
 * token's sight), read again whenever the scene's room says something changed, and token moves. A move shows at
 * once and is put back if the server refuses it (a wall in the way).
 */
export function useSceneView(sceneId: string, tokenId?: string) {
  const client = useClient();
  const [data, setData] = useState<ViewState>({ state: 'loading' });
  const [problem, setProblem] = useState<string | null>(null);

  const read = useCallback(async (): Promise<void> => {
    try {
      const answer = await client.post(`/v1/scene/${sceneId}/view`, { view: tokenId ? { token_id: tokenId } : {} });
      const view = viewSchema.parse(answer).view;
      // An uploaded map or portrait is the API's: at the client's base, with the session cookie.
      setData({
        state: 'ready',
        view: {
          ...view,
          background_url: pictureUrl(client, view.background_url),
          tokens: view.tokens.map((one) => ({ ...one, picture_url: pictureUrl(client, one.picture_url) })),
        },
      });
    } catch (error) {
      const failed = error instanceof Error ? error : new Error(String(error));
      setData((current) => (current.state === 'ready' ? current : { state: 'failed', error: failed }));
    }
  }, [client, sceneId, tokenId]);

  useEffect(() => {
    // The first read from a callback: the effect subscribes, the reads set state.
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  // Live: anything on the scene changes in its room (never its data, so a hidden token's move gives
  // nothing away); each change reads the view again, where the server decides what this person sees.
  const room = useMemo(() => ({ type: 'scene', id: sceneId }), [sceneId]);
  const live = useRoom(room, () => void read(), { onReset: () => void read() });

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

  // The GM opens a closed (or locked, or barred) door and closes an open one; the room tells every view.
  const toggleDoor = async (wall: ViewWall): Promise<void> => {
    const next = wall.door_state === 'open' ? 'closed' : 'open';
    // The stored wall first: the update carries its version, so a change made meanwhile isn't overwritten.
    const failed = await writeProblem(
      client
        .get(`/v1/scene_wall/${wall.id}`)
        .then((answer: unknown) =>
          client.put(`/v1/scene_wall/${wall.id}`, { scene_wall: { door_state: next } }, storedWall.parse(answer).scene_wall),
        ),
      next === 'open' ? 'The door didn’t open' : 'The door didn’t close',
    );
    setProblem(failed);
    await read();
  };

  return {
    data,
    live,
    problem,
    move,
    toggleDoor,
    retry: (): Promise<void> => {
      setData({ state: 'loading' });
      return read();
    },
  };
}
