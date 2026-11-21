// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The pieces of the play screen's "Table" panel, each by campaign id (rpg-ai mounts the VTT's pages
 * without nav, and puts the table in its play area):
 * - SceneList: the campaign's scenes, the current one marked; the GM makes another current;
 * - CampaignSeats: the seats of the campaign's table;
 * - CurrentSceneTokens: the tokens of the current scene as a list, the map's list on its own.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useClient, useUser, writeProblem } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';
import { TokenList } from '../scene/SceneView';
import { useSceneView } from '../scene/useSceneView';
import { SeatList } from '../seats/SeatList';

const sceneSchema = z.object({ id: z.string(), name: z.string().nullish(), is_active: z.boolean().nullish() }).passthrough();
const campaignSchema = z.object({
  campaign: z
    .object({ id: z.string(), user_id: z.string().nullish(), created_by_user_id: z.string().nullish() })
    .passthrough(),
});
const tableSchema = z.object({ id: z.string(), conversation_id: z.string().nullish() }).passthrough();
const currentSchema = z.object({ scene: z.object({ id: z.string() }).nullable() });

type Scene = z.infer<typeof sceneSchema>;
type Loaded<T> = { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; value: T };

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

/** Whether the signed-in person is the campaign's GM (its owner, or its creator). Buttons only. */
function useIsGm(campaignId: string): boolean {
  const client = useClient();
  const user = useUser();
  const [owners, setOwners] = useState<string[]>([]);
  useEffect(() => {
    let live = true;
    void client
      .get(`/v1/campaign/${campaignId}`)
      .then((answer: unknown) => {
        const campaign = campaignSchema.parse(answer).campaign;
        if (live) setOwners([campaign.user_id, campaign.created_by_user_id].filter((one): one is string => Boolean(one)));
      })
      .catch(() => live && setOwners([]));
    return () => {
      live = false;
    };
  }, [client, campaignId]);
  const me = user.data?.id;
  return me ? owners.includes(me) : !user.error && owners.length > 0;
}

export function SceneList({ campaignId }: { campaignId: string }): ReactNode {
  const client = useClient();
  const gm = useIsGm(campaignId);
  const [data, setData] = useState<Loaded<Scene[]>>({ state: 'loading' });
  const [problem, setProblem] = useState<string | null>(null);
  const read = useCallback(
    (): Promise<void> =>
      client
        .list('/v1/scene', 'scenes', sceneSchema, { campaign_id: campaignId })
        .then((value: Scene[]) => setData({ state: 'ready', value }))
        .catch((error: unknown) => setData({ state: 'failed', error: asError(error) })),
    [client, campaignId],
  );
  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);
  if (data.state === 'loading') return <SkeletonRows rows={3} label='Loading the scenes' />;
  if (data.state === 'failed') return <LoadProblem what='the scenes' error={data.error} onRetry={read} />;
  if (data.value.length === 0) return <p className='text-muted-foreground text-sm'>No scenes yet.</p>;
  return (
    <section aria-label='Scenes' className='space-y-2'>
      <ul className='divide-border divide-y'>
        {data.value.map((one) => (
          <li key={one.id} className='flex min-h-11 items-center gap-2 py-1'>
            <span className='font-medium'>{one.name ?? 'Untitled scene'}</span>
            {one.is_active ? <span className='text-muted-foreground text-xs'>Current</span> : null}
            {gm && !one.is_active && (
              <Button
                type='button'
                variant='outline'
                size='sm'
                className='ms-auto min-h-11'
                onClick={() => {
                  void writeProblem(
                    client.post(`/v1/scene/${one.id}/activate`, { activate: {} }).then(() => read()),
                    `${one.name ?? 'That scene'} wasn't made current`,
                  ).then(setProblem);
                }}
              >
                Make current
              </Button>
            )}
          </li>
        ))}
      </ul>
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}

export function CampaignSeats({
  campaignId,
  personHref,
  onWhisper,
}: {
  campaignId: string;
  personHref?: (personId: string) => string | null;
  onWhisper?: (conversationId: string) => void;
}): ReactNode {
  const client = useClient();
  const [data, setData] = useState<Loaded<string | null>>({ state: 'loading' });
  const read = useCallback(
    (): Promise<void> =>
      client
        .list('/v1/table', 'tables', tableSchema, { campaign_id: campaignId })
        .then((tables: z.infer<typeof tableSchema>[]) =>
          setData({ state: 'ready', value: tables[0]?.conversation_id ?? null }),
        )
        .catch((error: unknown) => setData({ state: 'failed', error: asError(error) })),
    [client, campaignId],
  );
  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);
  if (data.state === 'loading') return <SkeletonRows rows={3} label='Loading the table' />;
  if (data.state === 'failed') return <LoadProblem what='the table' error={data.error} onRetry={read} />;
  if (data.value === null) return <p className='text-muted-foreground text-sm'>This campaign has no table yet.</p>;
  return <SeatList conversationId={data.value} personHref={personHref} onWhisper={onWhisper} />;
}

function SceneTokens({
  sceneId,
  personHref,
}: {
  sceneId: string;
  personHref?: (personId: string) => string | null;
}): ReactNode {
  const scene = useSceneView(sceneId);
  if (scene.data.state === 'loading') return <SkeletonRows rows={3} label='Loading the tokens' />;
  if (scene.data.state === 'failed') return <LoadProblem what='the tokens' error={scene.data.error} onRetry={scene.retry} />;
  if (scene.data.view.tokens.length === 0) return <p className='text-muted-foreground text-sm'>No one is on this scene.</p>;
  return (
    <>
      <TokenList view={scene.data.view} personHref={personHref} onMove={(token, x, y) => void scene.move(token, x, y)} />
      {scene.problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {scene.problem}
        </p>
      )}
    </>
  );
}

export function CurrentSceneTokens({
  campaignId,
  personHref,
}: {
  campaignId: string;
  personHref?: (personId: string) => string | null;
}): ReactNode {
  const client = useClient();
  const [scene, setScene] = useState<Loaded<string | null>>({ state: 'loading' });
  const read = useCallback(
    (): Promise<void> =>
      client
        .post('/v1/scene/current', { current: { campaign_id: campaignId } })
        .then((answer: unknown) => setScene({ state: 'ready', value: currentSchema.parse(answer).scene?.id ?? null }))
        .catch((error: unknown) => setScene({ state: 'failed', error: asError(error) })),
    [client, campaignId],
  );
  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);
  if (scene.state === 'loading') return <SkeletonRows rows={3} label='Loading the current scene' />;
  if (scene.state === 'failed') return <LoadProblem what='the current scene' error={scene.error} onRetry={read} />;
  if (scene.value === null)
    return <p className='text-muted-foreground text-sm'>No current scene: the GM makes one current.</p>;
  return <SceneTokens sceneId={scene.value} personHref={personHref} />;
}
