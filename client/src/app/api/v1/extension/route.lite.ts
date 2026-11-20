// SPDX-License-Identifier: AGPL-3.0-or-later
import { NextResponse } from 'next/server';

/**
 * The server-side extensions this API serves, as server-framework lists its own
 * (`GET /v1/extension`). The UI turns a feature on when the extension serving it is listed, so lite
 * lists what its own routes answer: rpg_state's game systems and campaigns. Accounts and plans stay
 * off because their extensions are absent.
 */
export const LITE_EXTENSIONS = [
  {
    id: 'lite-rpg_state',
    name: 'rpg_state',
    friendly_name: 'Campaigns',
    description: 'Game systems and campaigns',
  },
] as const;

export function GET(): NextResponse {
  return NextResponse.json({ extensions: LITE_EXTENSIONS });
}
