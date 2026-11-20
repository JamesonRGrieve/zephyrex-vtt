// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PLANNED } from '~/content/marketing';
import { Landing } from './Landing';

describe('Landing', () => {
  it('has one h1, what works today, what is planned and the way in', () => {
    render(<Landing />);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('region', { name: 'What it does today' })).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Open your table' })[0]).toHaveAttribute('href', '/rpg');
  });

  it('marks every planned feature as planned', () => {
    render(<Landing />);
    const planned = within(screen.getByRole('region', { name: 'What is planned' }));
    const titles = planned.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent);
    expect(titles).toHaveLength(PLANNED.length);
    for (const title of titles) expect(title).toMatch(/^Planned: /);
  });

  it('takes the way in it is given', () => {
    render(<Landing start={{ label: 'Sign in', href: '/user' }} />);
    expect(screen.getAllByRole('link', { name: 'Sign in' })[0]).toHaveAttribute('href', '/user');
  });
});
