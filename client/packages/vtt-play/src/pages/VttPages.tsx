// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The VTT's pages for an app's router (vttExtension): campaigns, a campaign's table (its current
 * scene and seats), a scene, a character's sheet, and the game systems with their installed modules.
 * Each page shows the four states. Characters link to their wiki pages when the app says how
 * (`personHref`), and the wiki links back with sheetPath.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { useClient } from 'zephyrex';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';
import { campaignPath, scenePath } from '../paths';
import { SceneView } from '../scene/SceneView';
import { SeatList } from '../seats/SeatList';
import { CharacterSheet } from '../sheet/CharacterSheet';
import { useList, type ListState } from './useList';

export type PersonHref = (personId: string) => string | null;

const campaignSchema = z.object({ id: z.string(), name: z.string().nullish() }).passthrough();
const tableSchema = z
  .object({ id: z.string(), name: z.string().nullish(), conversation_id: z.string().nullish() })
  .passthrough();
const systemSchema = z.object({ id: z.string(), name: z.string().nullish(), slug: z.string().nullish() }).passthrough();
const moduleSchema = z
  .object({ id: z.string(), name: z.string().nullish(), line: z.string().nullish(), document_count: z.number().nullish() })
  .passthrough();
const currentSchema = z.object({ scene: z.object({ id: z.string(), name: z.string().nullish() }).nullable() });

function Rows<T>({
  data,
  retry,
  what,
  empty,
  children,
}: {
  data: ListState<T>;
  retry: () => Promise<void>;
  what: string;
  empty: string;
  children: (rows: T[]) => ReactNode;
}): ReactNode {
  if (data.state === 'loading') return <SkeletonRows rows={4} label={`Loading ${what}`} />;
  if (data.state === 'failed') return <LoadProblem what={what} error={data.error} onRetry={retry} />;
  if (data.rows.length === 0) return <p className='text-muted-foreground text-sm'>{empty}</p>;
  return children(data.rows);
}

function Page({ title, children }: { title: string; children: ReactNode }): ReactNode {
  return (
    <main className='mx-auto w-full min-w-0 max-w-4xl space-y-6 px-4 py-6'>
      <h1 className='text-2xl font-semibold'>{title}</h1>
      {children}
    </main>
  );
}

export function CampaignsPage({ base }: { base: string }): ReactNode {
  const { data, retry } = useList('/v1/campaign', 'campaigns', campaignSchema);
  return (
    <Page title='Tables'>
      <Rows data={data} retry={retry} what='your campaigns' empty='No campaigns yet.'>
        {(rows) => (
          <ul className='divide-border divide-y'>
            {rows.map((one) => (
              <li key={one.id} className='py-2'>
                <a href={campaignPath(base, one.id)} className='font-medium underline-offset-4 hover:underline'>
                  {one.name ?? 'Untitled campaign'}
                </a>
              </li>
            ))}
          </ul>
        )}
      </Rows>
    </Page>
  );
}

export function CampaignTablePage({
  base,
  campaignId,
  personHref,
}: {
  base: string;
  campaignId: string;
  personHref?: PersonHref;
}): ReactNode {
  const client = useClient();
  const [scene, setScene] = useState<{ id: string; name?: string | null } | null | undefined>(undefined);
  const tables = useList('/v1/table', 'tables', tableSchema, { campaign_id: campaignId });
  useEffect(() => {
    let live = true;
    void client
      .post('/v1/scene/current', { current: { campaign_id: campaignId } })
      .then((answer: unknown) => live && setScene(currentSchema.parse(answer).scene))
      .catch(() => live && setScene(null));
    return () => {
      live = false;
    };
  }, [client, campaignId]);
  return (
    <Page title='The table'>
      <section aria-label='Current scene' className='space-y-2'>
        {scene === undefined ? (
          <SkeletonRows rows={3} label='Loading the current scene' />
        ) : scene === null ? (
          <p className='text-muted-foreground text-sm'>No current scene: the GM activates one.</p>
        ) : (
          <>
            <a href={scenePath(base, scene.id)} className='text-sm underline-offset-4 hover:underline'>
              {scene.name ?? 'The scene'}
            </a>
            <SceneView sceneId={scene.id} personHref={personHref} />
          </>
        )}
      </section>
      <Rows data={tables.data} retry={tables.retry} what='the tables' empty='No table for this campaign yet.'>
        {(rows) =>
          rows.map((one) =>
            one.conversation_id ? (
              <section key={one.id} aria-label={one.name ?? 'Table'} className='space-y-2'>
                <h2 className='text-lg font-semibold'>{one.name ?? 'Table'}</h2>
                <SeatList conversationId={one.conversation_id} personHref={personHref} />
              </section>
            ) : null,
          )
        }
      </Rows>
    </Page>
  );
}

export function ScenePage({ sceneId, personHref }: { sceneId: string; personHref?: PersonHref }): ReactNode {
  return (
    <Page title='Scene'>
      <SceneView sceneId={sceneId} personHref={personHref} />
    </Page>
  );
}

export function SheetPage({ personId, personHref }: { personId: string; personHref?: PersonHref }): ReactNode {
  const wiki = personHref?.(personId) ?? null;
  return (
    <Page title='Character sheet'>
      {wiki && (
        <a href={wiki} className='text-sm underline-offset-4 hover:underline'>
          Open their wiki page
        </a>
      )}
      <CharacterSheet personId={personId} />
    </Page>
  );
}

export function SystemsPage(): ReactNode {
  const systems = useList('/v1/game_system', 'game_systems', systemSchema);
  const modules = useList('/v1/content_module', 'content_modules', moduleSchema);
  return (
    <Page title='Game systems'>
      <Rows data={systems.data} retry={systems.retry} what='the game systems' empty='No game systems yet.'>
        {(rows) => (
          <ul className='grid gap-2 sm:grid-cols-2'>
            {rows.map((one) => (
              <li key={one.id} className='border-border rounded-md border p-3'>
                {one.name ?? one.slug ?? 'Unnamed system'}
              </li>
            ))}
          </ul>
        )}
      </Rows>
      <section aria-label='Installed modules' className='space-y-2'>
        <h2 className='text-lg font-semibold'>Your installed modules</h2>
        <Rows data={modules.data} retry={modules.retry} what='your modules' empty='No modules installed for your account.'>
          {(rows) => (
            <ul className='divide-border divide-y'>
              {rows.map((one) => (
                <li key={one.id} className='flex justify-between py-2'>
                  <span>{one.name ?? one.line ?? 'Module'}</span>
                  <span className='text-muted-foreground text-sm'>{one.document_count ?? 0} documents</span>
                </li>
              ))}
            </ul>
          )}
        </Rows>
      </section>
    </Page>
  );
}
