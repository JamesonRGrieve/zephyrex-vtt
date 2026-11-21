// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The VTT as a client extension, for any app that composes it (rpg-ai, beside the wiki's
 * wikiExtension): its pages under `base` ("vtt" by default) and nav entries. Each section shows only
 * when GET /v1/extension lists the server extension that serves it. Not a client module: an app's
 * config, which builds this, is read on the server too (and by its proxy), so the pages load lazily
 * and this module pulls in nothing of the play UI. Import it as `@zephyrex/vtt-play/extension`.
 */
import { lazy, Suspense, type ComponentType, type ReactElement } from 'react';
import type { ZephyrexClientExtension } from 'zephyrex';
import type { PersonHref } from './pages/VttPages';
import { systemsPath, vttRoot } from './paths';

export { campaignPath, scenePath, sheetPath, systemsPath, vttRoot } from './paths';

const pages = () => import('./pages/VttPages');
const CampaignsPage = lazy(() => pages().then((module) => ({ default: module.CampaignsPage })));
const CampaignTablePage = lazy(() => pages().then((module) => ({ default: module.CampaignTablePage })));
const ScenePage = lazy(() => pages().then((module) => ({ default: module.ScenePage })));
const SheetPage = lazy(() => pages().then((module) => ({ default: module.SheetPage })));
const SystemsPage = lazy(() => pages().then((module) => ({ default: module.SystemsPage })));
const LazySettingSystems = lazy(() => pages().then((module) => ({ default: module.SettingSystems })));

/**
 * A setting's game systems and installed modules, for the wiki's setting page (Settings → <setting>
 * → Game systems): a host passes it into the wiki's setting slot. Loads its page code lazily.
 */
export function SettingSystems({ settingId }: { settingId: string }): ReactElement {
  return (
    <Suspense fallback={null}>
      <LazySettingSystems settingId={settingId} />
    </Suspense>
  );
}

type RoutedProps = { params: Record<string, string>; searchParams: Record<string, string> };

function routed(render: (params: Record<string, string>) => ReactElement): ComponentType<RoutedProps> {
  function VttRoute({ params }: RoutedProps): ReactElement {
    return <Suspense fallback={null}>{render(params)}</Suspense>;
  }
  return VttRoute;
}

const of = (params: Record<string, string>, name: string): string => params[name] ?? '';

export interface VttExtensionOptions {
  /** Where the pages live: "vtt" by default. */
  base?: string;
  /** A character's wiki page (the wiki's recordPath), for names to link to. */
  personHref?: PersonHref;
  /** false: mount the pages without nav entries (a host reaches them its own way). */
  nav?: boolean;
}

export function vttExtension({ base = 'vtt', personHref, nav = true }: VttExtensionOptions = {}): ZephyrexClientExtension {
  const root = vttRoot(base).slice(1);
  return {
    name: 'rpg_scene',
    serverExtension: 'rpg_scene',
    displayName: 'Zephyrex VTT',
    description: 'Tables, scenes, character sheets and game systems',
    // Most specific first: the router takes the first pattern that matches.
    pages: [
      { path: `${root}/systems`, component: routed(() => <SystemsPage />) },
      {
        path: `${root}/scene/:scene`,
        component: routed((params) => <ScenePage sceneId={of(params, 'scene')} personHref={personHref} />),
      },
      {
        path: `${root}/sheet/:person`,
        component: routed((params) => <SheetPage personId={of(params, 'person')} personHref={personHref} />),
      },
      {
        path: `${root}/campaign/:campaign`,
        component: routed((params) => (
          <CampaignTablePage base={base} campaignId={of(params, 'campaign')} personHref={personHref} />
        )),
      },
      { path: root, component: routed(() => <CampaignsPage base={base} />) },
    ],
    navItems: nav
      ? [
          { title: 'Tables', url: vttRoot(base) },
          { title: 'Game systems', url: systemsPath(base) },
        ]
      : [],
  };
}
