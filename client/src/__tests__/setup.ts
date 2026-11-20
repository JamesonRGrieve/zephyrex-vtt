// SPDX-License-Identifier: AGPL-3.0-or-later
import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  })),
  usePathname: vi.fn(() => '/'),
  useSearchParams: vi.fn(() => new URLSearchParams()),
  redirect: vi.fn(),
}));

// The app reads the JS-readable zx_csrf session cookie via the client entrypoint.
vi.mock('cookies-next/client', () => ({
  getCookie: vi.fn(() => undefined),
  setCookie: vi.fn(),
  deleteCookie: vi.fn(),
}));

// The jsdom stand-ins (matchMedia, ResizeObserver, pointer capture) and the toast reset come from
// the framework: vitest.config.ts lists zephyrex/testing/setup before this file.
