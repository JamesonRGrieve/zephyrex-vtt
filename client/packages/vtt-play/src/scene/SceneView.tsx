// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A scene to play on: the map the server lets this person see (the GM's whole scene; a player's
 * token's sight) on SceneCanvas (pan, pinch and wheel zoom, dragging tokens). Under it, the tokens
 * as a list with step buttons, for keyboards, screen readers and small screens.
 */
import { useState, type ReactNode } from 'react';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { movable, SceneCanvas } from './SceneCanvas';
import type { SceneViewData, ViewToken } from './schemas';
import { useSceneView } from './useSceneView';

export interface SceneViewProps {
  sceneId: string;
  /** The token a player sees from; by default the GM's whole view or the player's first token. */
  tokenId?: string;
  /** A character's wiki page, for the token list's names. */
  personHref?: (personId: string) => string | null;
  /** Also list the tokens with step buttons under the map (an accessible page's choice; the map
   * itself takes taps and the keyboard, so play doesn't need it). */
  showList?: boolean;
  /** A long-press on a token: show its details. */
  onTokenDetails?: (token: ViewToken) => void;
}

const STEPS = [
  { label: 'north', dx: 0, dy: -1, glyph: '↑' },
  { label: 'west', dx: -1, dy: 0, glyph: '←' },
  { label: 'east', dx: 1, dy: 0, glyph: '→' },
  { label: 'south', dx: 0, dy: 1, glyph: '↓' },
] as const;

/** The tokens of a view as a list, with step buttons for the ones this person may move (keyboard,
 * screen readers, phones); names link to the wiki. Used under the map, and on its own. */
export function TokenList({
  view,
  personHref,
  onMove,
}: {
  view: SceneViewData;
  personHref?: (personId: string) => string | null;
  onMove: (token: ViewToken, x: number, y: number) => void;
}): ReactNode {
  const move = onMove;
  return (
    <ul aria-label='Tokens' className='divide-border divide-y'>
      {view.tokens.map((one) => {
        const href = one.person_id ? (personHref?.(one.person_id) ?? null) : null;
        return (
          <li key={one.id} className='flex min-h-11 flex-wrap items-center gap-2 py-1'>
            {href ? (
              <a href={href} className='font-medium underline-offset-4 hover:underline'>
                {one.name ?? 'Token'}
              </a>
            ) : (
              <span className='font-medium'>{one.name ?? 'Token'}</span>
            )}
            <span className='text-muted-foreground text-xs'>
              {one.mine ? 'Yours' : (one.disposition ?? '')}
              {one.is_hidden ? ' · hidden' : ''}
            </span>
            {movable(view, one) && (
              <span className='ms-auto flex gap-1'>
                {STEPS.map((step) => (
                  <Button
                    key={step.label}
                    type='button'
                    variant='outline'
                    size='sm'
                    className='min-h-11 min-w-11'
                    aria-label={`Move ${one.name ?? 'token'} ${step.label}`}
                    onClick={() => move(one, one.x + step.dx * view.grid_size, one.y + step.dy * view.grid_size)}
                  >
                    {step.glyph}
                  </Button>
                ))}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function SceneView({ sceneId, tokenId, personHref, showList = false, onTokenDetails }: SceneViewProps): ReactNode {
  const scene = useSceneView(sceneId, tokenId);
  const [announcement, setAnnouncement] = useState('');
  const { data } = scene;
  if (data.state === 'loading') return <SkeletonRows rows={4} label='Loading the scene' />;
  if (data.state === 'failed') return <LoadProblem what='the scene' error={data.error} onRetry={scene.retry} />;
  const { view } = data;
  const move = (one: ViewToken, x: number, y: number): void => {
    void scene.move(one, x, y);
    setAnnouncement(`${one.name ?? 'Token'} moved`);
  };

  return (
    <section aria-label={view.name ?? 'Scene'} className='space-y-3'>
      <SceneCanvas view={view} onMove={move} onTokenDetails={onTokenDetails} />
      {!view.lit && <p className='text-muted-foreground text-sm'>It’s dark here: you see only what’s lit or close.</p>}
      {scene.problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {scene.problem}
        </p>
      )}
      <p aria-live='polite' className='sr-only'>
        {announcement}
      </p>
      {showList && <TokenList view={view} personHref={personHref} onMove={move} />}
    </section>
  );
}

export { SceneCanvas } from './SceneCanvas';
