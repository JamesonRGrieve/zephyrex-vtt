// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The landing page's words. The layout is @zephyrex/marketing's; what it says is this app's. A
 * claim here describes what the app does today, or is marked "Planned" and comes from
 * docs/DESIGN.md's confirmed scope.
 */
import type { Faq, Feature, FooterColumn, Link } from '@zephyrex/marketing';

export const NAV: readonly Link[] = [
  { label: 'Today', href: '#today' },
  { label: 'Planned', href: '#planned' },
  { label: 'FAQ', href: '#faq' },
];

export const START: Link = { label: 'Open your table', href: '/rpg' };

export const HERO = {
  title: 'Your table, on your own machine',
  lead: 'A virtual tabletop for any game system: campaigns, characters and their state today, with maps, scenes, tokens, dice and combat on the way. Run it at home for your group, or use the hosted service.',
};

/** What works now. */
export const TODAY: readonly Feature[] = [
  {
    id: 'campaigns',
    title: 'Campaigns and game systems',
    summary: 'Keep each campaign with the game system it runs on, and its game master.',
    details: ['Any system: you name it, nothing is built in', 'The same records in the home and hosted editions'],
    availability: 'everywhere',
  },
  {
    id: 'home',
    title: 'Runs at home',
    summary: 'The lite edition is one app on the game master’s machine, with its data in a file beside it.',
    details: ['No account and no subscription', 'Open source under the AGPL'],
    availability: 'everywhere',
  },
];

/** On the way, from the confirmed design (docs/DESIGN.md, Phases). Every card says so. */
export const PLANNED: readonly Feature[] = [
  {
    id: 'sheets',
    title: 'Planned: sheets, dice and combat',
    summary: 'Character sheets for any system, real dice rolls and a combat tracker.',
    details: ['Traits, items and status effects that add up the same way every time', 'Rolls the table can see'],
    availability: 'everywhere',
  },
  {
    id: 'scenes',
    title: 'Planned: scenes and the table',
    summary: 'Maps with walls and doors, tokens, and what each character can actually see.',
    details: ['Fog of war and lighting', 'Players join from their own devices'],
    availability: 'everywhere',
  },
  {
    id: 'maps',
    title: 'Planned: the map editor',
    summary: 'Stamps, terrain, paths and rooms, exported to your world wiki.',
    details: ['Battlemaps, towns and regions', 'Variants of one map'],
    availability: 'everywhere',
  },
  {
    id: 'hosted',
    title: 'Planned: hosted tables',
    summary: 'Invite players by link, with voice and video at the table and your assets stored for you.',
    details: ['Plans with storage quotas'],
    availability: 'hosted',
  },
];

export const FAQS: readonly Faq[] = [
  {
    question: 'Can I play a full session with it today?',
    answer:
      'Not yet. Campaigns and game systems work now; the table itself (maps, tokens, dice and combat) is planned, as the cards above say.',
  },
  {
    question: 'Do my players need accounts?',
    answer:
      'In the home edition, not today: it has one local owner. Local accounts, so players can join from their own devices, are planned next. The hosted service has accounts.',
  },
  {
    question: 'Which game systems does it support?',
    answer: 'Any. A game system is something you name; the rules it uses are planned as system packs.',
  },
];

export const CLOSING = {
  title: 'Set up your campaign',
  body: 'Start with your campaign and its game system; the table follows.',
};

export const FOOTER: readonly FooterColumn[] = [
  {
    title: 'Zephyrex VTT',
    links: [
      { label: 'Source code', href: 'https://github.com/JamesonRGrieve/zephyrex-vtt' },
      { label: 'FAQ', href: '#faq' },
    ],
  },
];
