// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { SidebarHeader, SidebarHeaderTitle } from 'zephyrex/components/appwrapper/src/SidebarHeader';
import { PageHeader } from 'zephyrex/ui/page-header';
import { SidebarInset } from 'zephyrex/ui/sidebar';

/** A page that isn't there, in the app's frame (so a phone keeps its menu), with a way back. */
export default function NotFound(): ReactNode {
  return (
    <SidebarInset className='min-h-svh min-w-0'>
      <SidebarHeader>
        <SidebarHeaderTitle>Not found</SidebarHeaderTitle>
      </SidebarHeader>
      <div className='mx-auto grid w-full min-w-0 max-w-3xl gap-6 px-4 pb-8 pt-2'>
        <PageHeader title="This page isn't here" description='The link may be old, or the page may not be built yet.' />
        <p>
          <Link href='/' className='text-primary underline underline-offset-4'>
            Go to the start
          </Link>
        </p>
      </div>
    </SidebarInset>
  );
}
