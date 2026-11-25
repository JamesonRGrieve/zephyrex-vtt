// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The map play script, drawn (the operator, 2026-11-25: "Maps are still completely fucked and need a
 * whole testing framework on the part of VTT"). Each step of the server's play script
 * (EP_MapPlay_test: open in the parlour, the market, the watch house, an arrival, the cellar fight,
 * a departure) wrote the GM's view the server sent (MAP_PLAY_DIR); here SceneCanvas draws it at a
 * phone's and a desktop's width and the drawing is read back: the right scene, its map art under the
 * grid (its colour where no one stands), and every token on its own square (a disc, not the art,
 * at its centre). A screenshot of each is kept (MAP_PLAY_SHOTS) for the review the SOP asks.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

const HARNESS = process.env.MAP_PLAY_JS ?? '';
const DIR = process.env.MAP_PLAY_DIR ?? '';
const SHOTS = process.env.MAP_PLAY_SHOTS ?? '';

type Token = { id: string; name?: string | null; x: number; y: number; width?: number | null; height?: number | null };
type Step = {
  step: string;
  scene: string;
  art: [number, number, number];
  view: { name: string; width: number; height: number; grid_size: number; tokens: Token[] } & Record<string, unknown>;
};

const steps: Step[] = DIR
  ? readdirSync(DIR)
      .filter((name) => name.endsWith('.json'))
      .sort()
      .map((name) => JSON.parse(readFileSync(join(DIR, name), 'utf8')) as Step)
  : [];

const SIZES = [
  { label: 'phone', width: 412, height: 915, touch: true, scheme: 'dark' as const },
  { label: 'desktop', width: 1280, height: 800, touch: false, scheme: 'light' as const },
];

async function open(page: Page, step: Step, dark: boolean): Promise<void> {
  await page.setContent(
    `<!doctype html><html class="${dark ? 'dark' : ''}"><head><meta name="viewport" content="width=device-width,initial-scale=1">
     <style>:root{--muted:240 4.8% 95.9%;--border:240 5.9% 90%;--foreground:240 10% 3.9%;--primary:262 83% 58%;--primary-foreground:0 0% 98%;--muted-foreground:240 3.8% 46.1%}
     .dark{--muted:240 3.7% 15.9%;--foreground:0 0% 98%;--muted-foreground:240 5% 64.9%}
     body{margin:0;font-family:sans-serif}.min-h-64{min-height:16rem}.w-full{width:100%}.h-full{height:100%}.relative{position:relative}.overflow-hidden{overflow:hidden}.touch-none{touch-action:none}canvas{display:block}.max-h-\\[70svh\\]{max-height:70svh}</style>
     </head><body><div id="root"></div></body></html>`,
  );
  await page.evaluate((view) => Object.assign(window, { vttView: view }), step.view);
  await page.addScriptTag({ content: readFileSync(HARNESS, 'utf8') });
  await expect(page.locator('canvas')).toHaveAttribute('data-camera', /.+/);
}

/** The pixel drawn at a scene point, read from the canvas itself. */
async function pixelAt(page: Page, x: number, y: number): Promise<[number, number, number, number]> {
  const [zoom, cx, cy] = ((await page.locator('canvas').getAttribute('data-camera')) ?? '').split(',').map(Number);
  return page.evaluate(
    ([px, py]) => {
      const canvas = document.querySelector('canvas')!;
      const ratio = canvas.width / canvas.getBoundingClientRect().width;
      const data = canvas.getContext('2d')!.getImageData(Math.round(px! * ratio), Math.round(py! * ratio), 1, 1).data;
      return [data[0]!, data[1]!, data[2]!, data[3]!] as [number, number, number, number];
    },
    [(x - cx!) * zoom!, (y - cy!) * zoom!],
  );
}

function near(colour: number[], art: number[], within: number): boolean {
  return colour.slice(0, 3).every((value, index) => Math.abs(value - art[index]!) <= within);
}

/** A square's centre with no token within three squares: where only the art (and the faint grid's
 * cell interior) is drawn. */
function emptyCell(step: Step): [number, number] {
  const grid = step.view.grid_size;
  const columns = Math.floor(step.view.width / grid);
  const rows = Math.floor(step.view.height / grid);
  let best: [number, number] = [grid / 2, grid / 2];
  let far = -1;
  for (let cx = 1; cx < columns - 1; cx += 1) {
    for (let cy = 1; cy < rows - 1; cy += 1) {
      const nearest = Math.min(
        ...step.view.tokens.map((one) => Math.max(Math.abs(one.x / grid - cx), Math.abs(one.y / grid - cy))),
        Number.POSITIVE_INFINITY,
      );
      if (nearest > far) {
        far = nearest;
        best = [(cx + 0.5) * grid, (cy + 0.5) * grid];
      }
    }
  }
  return best;
}

test.skip(!HARNESS || steps.length === 0, 'MAP_PLAY_JS and MAP_PLAY_DIR (the server play script’s export) are needed');

for (const size of SIZES) {
  test.describe(`${size.label} ${size.width}×${size.height}`, () => {
    test.use({
      viewport: { width: size.width, height: size.height },
      hasTouch: size.touch,
      isMobile: size.touch,
      colorScheme: size.scheme,
    });

    for (const step of steps) {
      test(`${step.step}: ${step.scene}, its art and everyone on their square`, async ({ page }) => {
        await open(page, step, size.scheme === 'dark');
        await expect(page.getByRole('application', { name: new RegExp(`Map of ${step.scene}`) })).toBeVisible();
        // The art under the grid, where no one stands.
        const [ex, ey] = emptyCell(step);
        await expect
          .poll(async () => near(await pixelAt(page, ex, ey), step.art, 48), { message: 'the map art is drawn' })
          .toBe(true);
        // No two people on one square (the first review found three on one: the discs hid each other).
        const grid = step.view.grid_size;
        const squares = step.view.tokens.map((one) => `${Math.floor(one.x / grid)},${Math.floor(one.y / grid)}`);
        expect(new Set(squares).size, `squares ${squares.join(' ')}`).toBe(squares.length);
        // Every disc as drawn (spread from its square where it would cover a neighbour, as on a phone
        // over a whole town): none overlaps another, each is drawn (not the art at its centre) and
        // stays beside its own square.
        const discs = ((await page.locator('canvas').getAttribute('data-discs')) ?? '')
          .split(' ')
          .filter(Boolean)
          .map((one) => {
            const [id, rest] = one.split(':');
            const [cx, cy, r] = rest!.split(',').map(Number);
            return { id: id!, cx: cx!, cy: cy!, r: r! };
          });
        expect(discs.map((one) => one.id).sort()).toEqual(step.view.tokens.map((one) => one.id).sort());
        for (const [index, a] of discs.entries()) {
          for (const b of discs.slice(index + 1)) {
            expect(Math.hypot(a.cx - b.cx, a.cy - b.cy), `${a.id} and ${b.id} overlap`).toBeGreaterThanOrEqual(
              a.r + b.r - 0.5,
            );
          }
        }
        const [zoom, camX, camY] = ((await page.locator('canvas').getAttribute('data-camera')) ?? '').split(',').map(Number);
        for (const token of step.view.tokens) {
          const disc = discs.find((one) => one.id === token.id)!;
          const sceneX = disc.cx / zoom! + camX!;
          const sceneY = disc.cy / zoom! + camY!;
          const drawn = await pixelAt(page, sceneX, sceneY);
          expect(near(drawn, step.art, 24), `${token.name ?? token.id} drawn at its disc`).toBe(false);
          const square = [
            (token.x + ((token.width ?? 1) * grid) / 2 - camX!) * zoom!,
            (token.y + ((token.height ?? 1) * grid) / 2 - camY!) * zoom!,
          ];
          expect(
            Math.hypot(disc.cx - square[0]!, disc.cy - square[1]!),
            `${token.name ?? token.id} near its square`,
          ).toBeLessThanOrEqual(disc.r * 3);
        }
        if (SHOTS) await page.screenshot({ path: join(SHOTS, `${size.label}-${step.step}.png`) });
      });
    }
  });
}
