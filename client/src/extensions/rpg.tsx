// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import type { ReactNode } from 'react';
import type { ZephyrexClientExtension } from 'zephyrex';
import { SidebarHeader, SidebarHeaderTitle } from 'zephyrex/components/appwrapper/src/SidebarHeader';
import { PageHeader } from 'zephyrex/ui/page-header';
import { SidebarInset } from 'zephyrex/ui/sidebar';

/**
 * The app's home. It says what the app holds today and nothing it doesn't: the campaign and game
 * system screens are the next items in docs/DESIGN.md, and this page lists them once they land.
 * It sits in the framework's inset (a column: the top bar, with the phone's menu button, above
 * the page), as rpg-ai's AppPage does.
 */
function RPGDashboard(): ReactNode {
  return (
    <SidebarInset className='min-h-svh min-w-0'>
      <SidebarHeader>
        <SidebarHeaderTitle>Home</SidebarHeaderTitle>
      </SidebarHeader>
      <div className='mx-auto grid w-full min-w-0 max-w-3xl gap-6 px-4 pb-8 pt-2'>
        <PageHeader
          title='Zephyrex VTT'
          description='Your campaigns and the game systems they run on are kept here. Their screens are being built next; maps, scenes, dice and the live table follow.'
        />
      </div>
    </SidebarInset>
  );
}

export const rpgExtension: ZephyrexClientExtension = {
  name: 'rpg',
  displayName: 'Zephyrex VTT',
  description: 'Campaigns and game systems today; maps, scenes, dice and the live table on the way.',
  serverExtension: 'rpg_state',
  pages: [{ path: 'rpg', component: RPGDashboard }],
  navItems: [{ title: 'Home', url: '/rpg' }],
};
