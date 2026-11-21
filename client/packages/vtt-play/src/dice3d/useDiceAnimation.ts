// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useSyncExternalStore } from 'react';

const KEY = 'zephyrex-vtt:dice-animation';
const REDUCED = '(prefers-reduced-motion: reduce)';

function subscribe(changed: () => void): () => void {
  const motion = window.matchMedia?.(REDUCED);
  window.addEventListener('storage', changed);
  motion?.addEventListener?.('change', changed);
  return () => {
    window.removeEventListener('storage', changed);
    motion?.removeEventListener?.('change', changed);
  };
}

function snapshot(): string {
  const reduced = window.matchMedia?.(REDUCED).matches === true;
  return `${window.localStorage.getItem(KEY) ?? 'on'}|${reduced ? 'reduced' : 'full'}`;
}

/**
 * Whether dice tumble on this device: its own setting (on unless turned off), and never when the
 * system asks for reduced motion. `chosen` is the setting itself, for the toggle.
 */
export function useDiceAnimation(): { animate: boolean; chosen: boolean; reduced: boolean; choose: (on: boolean) => void } {
  const [setting, motion] = useSyncExternalStore(subscribe, snapshot, () => 'on|full').split('|');
  const choose = useCallback((on: boolean) => {
    window.localStorage.setItem(KEY, on ? 'on' : 'off');
    window.dispatchEvent(new StorageEvent('storage', { key: KEY }));
  }, []);
  const chosen = setting !== 'off';
  const reduced = motion === 'reduced';
  return { animate: chosen && !reduced, chosen, reduced, choose };
}
