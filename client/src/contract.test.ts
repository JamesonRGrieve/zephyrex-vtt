// @vitest-environment node
// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The lite route handlers against contract/api-cases.json, the cases the SaaS server answers too
 * (server/extensions/rpg_state/EP_Contract_test.py), on a real database.
 */
import { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it } from 'vitest';
import contract from '../../contract/api-cases.json';
import * as campaignRecord from '~/app/api/v1/campaign/[id]/route.lite';
import * as campaignCollection from '~/app/api/v1/campaign/route.lite';
import * as gameSystemRecord from '~/app/api/v1/game_system/[id]/route.lite';
import * as gameSystemCollection from '~/app/api/v1/game_system/route.lite';
import { prisma } from '~/lib/prisma';

interface Expectation {
  status: number;
  body?: Record<string, unknown>;
  listed?: { key: string; id: string };
}

interface CaseRequest {
  method: string;
  path: string;
  headers?: Record<string, string>;
  body?: unknown;
  expect: Expectation;
  save?: string;
}

interface Case {
  name: string;
  requests: CaseRequest[];
}

type Handler = (request: NextRequest, context: { params: Promise<Record<string, string>> }) => Promise<Response>;
type Handlers = Partial<Record<string, Handler>>;

const ROUTES: Record<string, { collection: Handlers; record: Handlers }> = {
  game_system: { collection: gameSystemCollection, record: gameSystemRecord },
  campaign: { collection: campaignCollection, record: campaignRecord },
};

interface Saved {
  id: string;
  etag: string;
}

/** Replaces '{name.id}' and '{name.etag}' in every string inside `value`. */
function fill<T>(value: T, saved: Map<string, Saved>): T {
  if (typeof value === 'string') {
    return value.replace(/\{(\w+)\.(id|etag)\}/g, (_, name: string, part: 'id' | 'etag') => {
      const record = saved.get(name);
      if (record === undefined) throw new Error(`nothing saved as ${name}`);
      return record[part];
    }) as T;
  }
  if (Array.isArray(value)) return value.map((item: unknown) => fill(item, saved)) as T;
  if (typeof value === 'object' && value !== null) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, fill(item, saved)])) as T;
  }
  return value;
}

async function send(request: CaseRequest): Promise<Response> {
  const [, , resource, id] = request.path.split('/') as [string, string, string, string | undefined];
  const routes = ROUTES[resource];
  if (routes === undefined) throw new Error(`no lite route for ${request.path}`);
  const handler = (id === undefined ? routes.collection : routes.record)[request.method];
  if (handler === undefined) throw new Error(`no ${request.method} handler for ${request.path}`);
  const body = request.body === undefined ? {} : { body: JSON.stringify(request.body) };
  const next = new NextRequest(`http://localhost/api${request.path}`, {
    method: request.method,
    headers: { 'Content-Type': 'application/json', ...request.headers },
    ...body,
  });
  const params: Record<string, string> = id === undefined ? {} : { id };
  return handler(next, { params: Promise.resolve(params) });
}

beforeEach(async () => {
  await prisma.campaign.deleteMany();
  await prisma.gameSystem.deleteMany();
});

describe('contract/api-cases.json against the lite handlers', () => {
  it.each((contract as { cases: Case[] }).cases.map((one) => [one.name, one] as const))('%s', async (_, testCase) => {
    const saved = new Map<string, Saved>();
    for (const raw of testCase.requests) {
      const request = fill(raw, saved);
      const response = await send(request);
      const answer = response.status === 204 ? null : ((await response.json()) as Record<string, unknown>);
      expect(response.status, `${request.method} ${request.path}: ${JSON.stringify(answer)}`).toBe(request.expect.status);
      if (request.expect.body !== undefined) expect(answer).toMatchObject(request.expect.body);
      if (request.expect.listed !== undefined) {
        const listed = answer?.[request.expect.listed.key] as { id: string }[];
        expect(listed.map((one) => one.id)).toContain(request.expect.listed.id);
      }
      if (raw.save !== undefined && answer !== null) {
        const record = Object.values(answer).find((item) => typeof item === 'object' && item !== null && 'id' in item) as {
          id: string;
        };
        saved.set(raw.save, { id: record.id, etag: response.headers.get('etag') ?? '' });
      }
    }
  });
});
