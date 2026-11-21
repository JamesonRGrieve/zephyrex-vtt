// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The visual audit: every page, on both editions, at desktop 1366, tablet 768 and phone 390@2x, dark and
 * light; the hosted edition signed out (its visitor pages), the lite edition's app pages.
 *
 * Every shot is checked for what a person would notice without looking closely: no sideways
 * overflow, no page errors, nothing fetched from another host, no same-origin link that answers
 * 4xx or 5xx, exactly one h1, headings that never skip a level (one outline), a title, and
 * every image named. With VISUAL_AUDIT=<dir> it also saves each screenshot and what the page
 * reported beside it, for the review image by image:
 *
 *   VISUAL_AUDIT=<dir> playwright test e2e/audit.spec.ts --project lite --project saas
 *
 * (Taken from zephyrex-rpg-ai's audit, itself modelled on Zephyreader's: hard checks, no fixed sleeps,
 * and expect.soft so one run lists every failing shot.)
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { devices, expect, test, type Browser, type Page, type TestInfo } from '@playwright/test';

const AUDIT_DIR = process.env.VISUAL_AUDIT ?? '';
// Real devices (their user agents, touch and mobile behaviour), at the audit's sizes.
const VIEWPORTS = {
  desktop: { ...devices['Desktop Chrome'], viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 },
  tablet: { ...devices['iPad Mini'], viewport: { width: 768, height: 1024 }, deviceScaleFactor: 2 },
  phone: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 },
} as const;
const THEMES = ['dark', 'light'] as const;
/** A page that isn't there: shot for the not-found page, and the one page allowed to answer 404. */
const MISSING = '/no-such-page';
/** The hosted edition's pages for a visitor (its signed-in pages need the server). */
const VISITOR_PAGES = ['/', '/user', MISSING];
/** The lite edition's pages: it has one local owner, so / goes straight to the app. */
const APP_PAGES = ['/', '/rpg', MISSING];
/** The dev server's own badge is not part of the app: leave it out of the shots. */
const HIDE_DEV_TOOLS = 'nextjs-portal { display: none !important; }';
const PER_SHOT_MS = 15_000;

interface Report {
  path: string;
  status: number;
  title: string;
  overflow: number;
  h1: number;
  headingSkips: string[];
  unnamedImages: number;
  pageErrors: string[];
  consoleErrors: string[];
  foreignRequests: string[];
  brokenLinks: string[];
}

/** Each same-origin link's status, fetched once per URL (so once per edition) for the run. */
const linkStatus = new Map<string, Promise<number>>();

async function brokenLinks(page: Page, origin: string): Promise<string[]> {
  const hrefs = await page.evaluate(
    (here) =>
      [...document.querySelectorAll('a[href]')]
        .map((link) => new URL((link as HTMLAnchorElement).href, here))
        .filter((url) => url.origin === new URL(here).origin)
        .map((url) => `${url.origin}${url.pathname}${url.search}`),
    origin,
  );
  const broken: string[] = [];
  for (const href of new Set(hrefs)) {
    let pending = linkStatus.get(href);
    if (pending === undefined) {
      pending = page.request.get(href, { maxRedirects: 5 }).then((response) => response.status());
      linkStatus.set(href, pending);
    }
    const status = await pending;
    if (status >= 400) broken.push(`${href} (${status})`);
  }
  return broken;
}

/** Waits for what a screenshot shows to stop changing: fonts loaded, finite animations done. */
async function settled(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle');
  await page.evaluate(async () => {
    await document.fonts.ready;
    const finite = document
      .getAnimations()
      .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity));
    await Promise.all(finite.map((animation) => animation.finished.catch(() => undefined)));
  });
}

async function shoot(page: Page, origin: string, target: string, name: string): Promise<Report> {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const foreignRequests: string[] = [];
  const onPageError = (error: Error): void => void pageErrors.push(error.message);
  const onConsole = (message: { type(): string; text(): string }): void => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  };
  const onRequest = (request: { url(): string }): void => {
    const url = new URL(request.url());
    if (url.protocol.startsWith('http') && url.origin !== origin) foreignRequests.push(request.url());
  };
  page.on('pageerror', onPageError);
  page.on('console', onConsole);
  page.on('request', onRequest);
  try {
    const response = await page.goto(target);
    await page.addStyleTag({ content: HIDE_DEV_TOOLS });
    await settled(page);
    const facts = await page.evaluate(() => ({
      title: document.title,
      // The page may scroll inside a container (the framework shell's SidebarInset), where
      // sideways overflow never widens the document: count the page's own scroller too.
      overflow: Math.max(
        document.documentElement.scrollWidth - window.innerWidth,
        ...[...document.querySelectorAll<HTMLElement>('*')]
          .filter((element) => /(auto|scroll)/.test(getComputedStyle(element).overflowY))
          .filter((element) => element.scrollHeight > element.clientHeight)
          .sort((a, b) => b.scrollHeight - a.scrollHeight)
          .slice(0, 1)
          .map((scroller) => scroller.scrollWidth - scroller.clientWidth),
      ),
      h1: document.querySelectorAll('h1').length,
      // One outline: each heading at most one level below the one before it (h2 → h4 skips).
      headingSkips: [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].flatMap((heading, index, all) => {
        const level = Number(heading.tagName[1]);
        const before = index === 0 ? 0 : Number(all[index - 1].tagName[1]);
        return level > before + 1 ? [`h${before} → h${level} "${(heading.textContent ?? '').trim().slice(0, 40)}"`] : [];
      }),
      unnamedImages: [...document.querySelectorAll('img')].filter((image) => !image.hasAttribute('alt')).length,
    }));
    const report: Report = {
      path: target,
      status: response?.status() ?? 0,
      ...facts,
      pageErrors,
      consoleErrors,
      foreignRequests,
      brokenLinks: await brokenLinks(page, origin),
    };
    if (AUDIT_DIR !== '') {
      mkdirSync(AUDIT_DIR, { recursive: true });
      // A full-page shot sees only the document: unroll the page's own scroller (the tallest
      // element that scrolls vertically) so the shot holds the whole page, not its first screen.
      // (16 Worldviews' finding, from its client/e2e/support/audit.ts.)
      await page.evaluate(() => {
        const [scroller] = [...document.querySelectorAll<HTMLElement>('*')]
          .filter((element) => /(auto|scroll)/.test(getComputedStyle(element).overflowY))
          .filter((element) => element.scrollHeight > element.clientHeight)
          .sort((a, b) => b.scrollHeight - a.scrollHeight);
        if (scroller !== undefined) {
          scroller.style.height = 'auto';
          scroller.style.overflow = 'visible';
        }
      });
      await page.screenshot({ path: path.join(AUDIT_DIR, `${name}.png`), fullPage: true });
      writeFileSync(path.join(AUDIT_DIR, `${name}.json`), `${JSON.stringify(report, null, 2)}\n`);
    }
    return report;
  } finally {
    // Detached before the next shot, so one page's traffic never lands in another's report.
    page.off('pageerror', onPageError);
    page.off('console', onConsole);
    page.off('request', onRequest);
  }
}

function expectClean(report: Report): void {
  // A page that answers an error is a defect even when it renders one tidy h1 (the first audit's
  // /settings was a bare 404 that passed every other check).
  expect.soft(report.status, `${report.path}: HTTP status`).toBe(report.path === MISSING ? 404 : 200);
  expect.soft(report.overflow, `${report.path}: sideways overflow`).toBeLessThanOrEqual(0);
  expect.soft(report.pageErrors, `${report.path}: page errors`).toEqual([]);
  expect.soft(report.foreignRequests, `${report.path}: requests to another host`).toEqual([]);
  expect.soft(report.brokenLinks, `${report.path}: broken links`).toEqual([]);
  expect.soft(report.h1, `${report.path}: h1 count`).toBe(1);
  expect.soft(report.headingSkips, `${report.path}: heading levels skipped`).toEqual([]);
  expect.soft(report.title, `${report.path}: title`).not.toBe('');
  expect.soft(report.unnamedImages, `${report.path}: images without alt`).toBe(0);
}

async function audit(browser: Browser, testInfo: TestInfo, pages: readonly string[], who: string): Promise<void> {
  const origin = String(testInfo.project.use.baseURL);
  for (const [size, device] of Object.entries(VIEWPORTS)) {
    for (const theme of THEMES) {
      const context = await browser.newContext({ ...device, baseURL: origin });
      await context.addCookies([{ name: 'theme', value: theme, url: origin }]);
      const page = await context.newPage();
      try {
        for (const target of pages) {
          const slug = target === '/' ? 'home' : target.slice(1).replaceAll('/', '-');
          const name = `${testInfo.project.name}-${who}-${size}-${theme}-${slug}`;
          expectClean(await shoot(page, origin, target, name));
        }
      } finally {
        await context.close();
      }
    }
  }
}

test.describe('visual audit', () => {
  test('the hosted edition, for a visitor', async ({ browser }, testInfo) => {
    test.skip(testInfo.project.name !== 'saas', 'the lite edition has no visitor pages');
    test.setTimeout(VISITOR_PAGES.length * 6 * PER_SHOT_MS + 30_000);
    await audit(browser, testInfo, VISITOR_PAGES, 'out');
  });

  test("the lite edition's pages", async ({ browser }, testInfo) => {
    test.skip(testInfo.project.name !== 'lite', "the hosted edition's app pages need a signed-in person");
    test.setTimeout(APP_PAGES.length * 6 * PER_SHOT_MS + 30_000);
    await audit(browser, testInfo, APP_PAGES, 'app');
  });
});
