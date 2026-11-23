// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The GM's map controls beside a scene: pick the campaign's scene to show (and make it the one the
 * players see), and place the cast on the map, each character not yet on it with a Place button.
 * Everything is the server's: the scenes and characters it lists, its activate and place routes;
 * the map redraws itself from the scene's room.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { Label } from 'zephyrex/ui/label';
import { z } from 'zod';
import type { SceneViewData } from './schemas';

const scenesSchema = z.object({
  scenes: z.array(z.object({ id: z.string(), name: z.string().nullish(), is_active: z.boolean().nullish() }).passthrough()),
});
const personsSchema = z.object({
  persons: z.array(z.object({ id: z.string(), name: z.string().nullish(), kind: z.string().nullish() }).passthrough()),
});

export interface MapControlsProps {
  campaignId: string;
  view: SceneViewData;
  /** The GM picked another scene: show it. */
  onScene?: (sceneId: string) => void;
}

export function MapControls({ campaignId, view, onScene }: MapControlsProps): ReactNode {
  const client = useClient();
  const [scenes, setScenes] = useState<z.infer<typeof scenesSchema>['scenes']>([]);
  const [cast, setCast] = useState<z.infer<typeof personsSchema>['persons']>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    const query = `campaign_id=${encodeURIComponent(campaignId)}`;
    const [found, people] = await Promise.all([client.get(`/v1/scene?${query}`), client.get(`/v1/person?${query}`)]);
    setScenes(scenesSchema.parse(found).scenes);
    setCast(personsSchema.parse(people).persons);
  }, [client, campaignId]);

  useEffect(() => {
    const first = window.setTimeout(() => {
      load().catch(() => setProblem('The scenes and cast didn’t load'));
    }, 0);
    return () => window.clearTimeout(first);
  }, [load]);

  const run = async (write: Promise<unknown>, fallback: string): Promise<void> => {
    setBusy(true);
    setProblem(
      await writeProblem(
        write.then(() => undefined),
        fallback,
      ),
    );
    setBusy(false);
  };

  const onMap = new Set(view.tokens.map((one) => one.person_id).filter(Boolean));
  const off = cast.filter((one) => !onMap.has(one.id));
  const current = scenes.find((one) => one.id === view.scene_id);

  return (
    <section aria-label='Map controls' className='space-y-3 rounded-lg border p-3'>
      <div className='flex flex-wrap items-end gap-2'>
        <div className='min-w-0 flex-1 space-y-1'>
          <Label htmlFor='map-controls-scene'>Scene</Label>
          <select
            id='map-controls-scene'
            value={view.scene_id}
            onChange={(event) => onScene?.(event.target.value)}
            className='border-input bg-background h-11 w-full rounded-md border px-3'
          >
            {scenes.map((one) => (
              <option key={one.id} value={one.id}>
                {one.name ?? 'Unnamed scene'}
                {one.is_active ? ' (showing)' : ''}
              </option>
            ))}
          </select>
        </div>
        <Button
          type='button'
          className='min-h-11'
          disabled={busy || current?.is_active === true}
          onClick={() =>
            void run(
              client.post(`/v1/scene/${view.scene_id}/activate`, { activate: {} }).then(load),
              'The scene wasn’t shown to the players',
            )
          }
        >
          {current?.is_active ? 'Showing to players' : 'Show to players'}
        </Button>
      </div>
      <div className='space-y-1'>
        <h3 className='text-sm font-medium'>Not on the map</h3>
        {off.length === 0 ? (
          <p className='text-muted-foreground text-sm'>Everyone in the campaign is on this map.</p>
        ) : (
          <ul className='divide-y rounded-md border'>
            {off.map((one) => (
              <li key={one.id} className='flex min-h-11 items-center justify-between gap-2 px-3'>
                <span>
                  {one.name ?? 'Unnamed'}
                  {one.kind ? <span className='text-muted-foreground text-xs'> ({one.kind})</span> : null}
                </span>
                <Button
                  type='button'
                  variant='outline'
                  className='min-h-11'
                  disabled={busy}
                  aria-label={`Place ${one.name ?? 'this character'} on the map`}
                  onClick={() =>
                    void run(
                      client.post(`/v1/scene/${view.scene_id}/place`, { place: { person_id: one.id } }),
                      `${one.name ?? 'The character'} wasn’t placed`,
                    )
                  }
                >
                  Place
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}
