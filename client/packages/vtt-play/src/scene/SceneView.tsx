// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A scene to play on: the map the server lets this person see (the GM's whole scene; a player's
 * token's sight) on SceneCanvas (pan, pinch and wheel zoom, dragging tokens). Above it, the tools:
 * move tokens, or measure. The GM taps a door to open or close it and, given the campaign, has the
 * map controls (the scene to show, the cast to place). Under it, the tokens as a list with step
 * buttons, for keyboards, screen readers and small screens.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { chipGroup } from 'zephyrex/hooks/chipKeys';
import { Button } from 'zephyrex/ui/button';
import { ChoiceChip } from 'zephyrex/ui/choice-chip';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { MapControls } from './MapControls';
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
  /** The scene's campaign: with it, the GM gets the map controls (the scene to show, the cast to place). */
  campaignId?: string;
  /** The GM picked another scene in the map controls. */
  onScene?: (sceneId: string) => void;
  /** The map fills its container's height (SceneCanvas fill). */
  fill?: boolean;
}

const TOOLS = [
  { tool: 'select', label: 'Move' },
  { tool: 'measure', label: 'Measure' },
] as const;

function ToolBar({ tool, onTool }: { tool: 'select' | 'measure'; onTool: (tool: 'select' | 'measure') => void }): ReactNode {
  const chips = useRef<HTMLDivElement>(null);
  useEffect(() => chipGroup(chips.current), []);
  return (
    <div ref={chips} role='radiogroup' aria-label='Map tool' className='flex flex-wrap gap-2'>
      {TOOLS.map((one) => (
        <ChoiceChip key={one.tool} checked={tool === one.tool} onClick={() => onTool(one.tool)}>
          {one.label}
        </ChoiceChip>
      ))}
    </div>
  );
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

export function SceneView({
  sceneId,
  tokenId,
  personHref,
  showList = false,
  onTokenDetails,
  campaignId,
  onScene,
  fill = false,
}: SceneViewProps): ReactNode {
  const scene = useSceneView(sceneId, tokenId);
  const [announcement, setAnnouncement] = useState('');
  const [tool, setTool] = useState<'select' | 'measure'>('select');
  const { data } = scene;
  if (data.state === 'loading') return <SkeletonRows rows={4} label='Loading the scene' />;
  if (data.state === 'failed') return <LoadProblem what='the scene' error={data.error} onRetry={scene.retry} />;
  const { view } = data;
  const move = (one: ViewToken, x: number, y: number): void => {
    void scene.move(one, x, y);
    setAnnouncement(`${one.name ?? 'Token'} moved`);
  };

  return (
    // Filling its host, the map takes the height the toolbar and notes leave.
    <section aria-label={view.name ?? 'Scene'} className={fill ? 'flex h-full flex-col gap-3' : 'space-y-3'}>
      {view.gm && campaignId && <MapControls campaignId={campaignId} view={view} onScene={onScene} />}
      <ToolBar tool={tool} onTool={setTool} />
      <div className={fill ? 'min-h-0 flex-1' : undefined}>
        <SceneCanvas
          view={view}
          onMove={move}
          onTokenDetails={onTokenDetails}
          tool={tool}
          onDoor={view.gm ? (wall) => void scene.toggleDoor(wall) : undefined}
          fill={fill}
        />
      </div>
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
