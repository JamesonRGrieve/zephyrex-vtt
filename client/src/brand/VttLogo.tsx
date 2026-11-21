// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ReactElement } from 'react';

/**
 * Zephyrex VTT's mark: a d20 standing on the table.
 * src/app/icon.svg is the same drawing in fixed colours, for the browser tab and the installed
 * app. Decorative: the app's name always stands beside it.
 */
export function VttLogo(): ReactElement {
  return (
    <svg viewBox='0 0 32 32' className='size-8' aria-hidden>
      <rect width='32' height='32' rx='7' className='fill-primary' />
      <path
        d='M4 25.5h24M8 22l-2 6M16 22v6M24 22l2 6'
        fill='none'
        strokeWidth='1.2'
        strokeLinecap='round'
        className='stroke-primary-foreground'
      />
      <path d='M16 3.5 25 8.5V18L16 23 7 18V8.5Z' className='fill-primary-foreground' />
      <path
        d='M16 8l4.6 8h-9.2ZM16 3.5V8M7 8.5 16 8l9 .5M7 18l4.4-2M25 18l-4.4-2M16 23l-4.6-7M16 23l4.6-7'
        fill='none'
        strokeWidth='1.1'
        strokeLinejoin='round'
        className='stroke-primary'
      />
    </svg>
  );
}
