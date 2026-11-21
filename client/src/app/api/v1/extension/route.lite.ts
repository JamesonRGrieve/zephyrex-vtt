// SPDX-License-Identifier: AGPL-3.0-or-later
import { NextResponse } from 'next/server';

/**
 * The server-side extensions this API serves, as server-framework lists its own
 * (`GET /v1/extension`). The UI turns a feature on when the extension serving it is listed, so lite
 * lists what its own routes answer: the wiki's rpg_core (campaigns) and rpg_systems (game systems).
 * Accounts and plans stay off because their extensions are absent.
 */
export const LITE_EXTENSIONS = [
  { id: 'lite-rpg_core', name: 'rpg_core', friendly_name: 'Campaigns', description: 'Campaigns' },
  { id: 'lite-rpg_systems', name: 'rpg_systems', friendly_name: 'Game systems', description: 'Game systems' },
] as const;

export function GET(): NextResponse {
  return NextResponse.json({ extensions: LITE_EXTENSIONS });
}
