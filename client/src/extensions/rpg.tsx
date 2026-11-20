// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import type { ZephyrexClientExtension } from 'zephyrex';

function RPGDashboard() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-4">Zephyrex VTT</h1>
      <p>Virtual tabletop on the Zephyrex framework: maps, scenes, tokens, sheets, dice, combat, live play.</p>
    </div>
  );
}

function RPGSettings() {
  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-2">RPG Settings</h2>
      <p>Configure your campaign extensions.</p>
    </div>
  );
}

export const rpgExtension: ZephyrexClientExtension = {
  name: 'rpg',
  displayName: 'Zephyrex VTT',
  description: 'Maps, scenes, tokens, sheets, dice, combat, live play',
  serverExtension: 'rpg_state',
  pages: [
    {
      path: 'rpg',
      component: RPGDashboard,
    },
  ],
  navItems: [
    {
      title: 'Zephyrex VTT',
      url: '/rpg',
    },
  ],
  settingsPanel: RPGSettings,
};
