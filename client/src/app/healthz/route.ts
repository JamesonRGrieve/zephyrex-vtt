// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The health probe the deployment's checks call (SOP Services: probes answer 204). It is the
 * client's own route in both editions, so a SaaS build answers it without proxying to the server,
 * unlike `/api/v1/alive`, which is lite-only. It says only that this Next server is up.
 */
export const dynamic = 'force-dynamic';

export function GET(): Response {
  return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
}
