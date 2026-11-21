// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The VTT pages' paths, in one place, for apps that link into them (the wiki's records link to a
 * character's sheet with sheetPath). A plain module: safe on the server. `base` is what
 * vttExtension({ base }) was given; 'vtt', '/vtt' and '/vtt/' all work.
 */
function root(base: string): string {
  return `/${base.replace(/^\/+|\/+$/g, '')}`;
}

const segment = (value: string): string => encodeURIComponent(value);

export function vttRoot(base: string): string {
  return root(base);
}

export function campaignPath(base: string, campaignId: string): string {
  return `${root(base)}/campaign/${segment(campaignId)}`;
}

export function scenePath(base: string, sceneId: string): string {
  return `${root(base)}/scene/${segment(sceneId)}`;
}

export function sheetPath(base: string, personId: string): string {
  return `${root(base)}/sheet/${segment(personId)}`;
}

export function systemsPath(base: string): string {
  return `${root(base)}/systems`;
}
