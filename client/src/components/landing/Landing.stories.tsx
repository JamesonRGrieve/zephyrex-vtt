// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { Landing } from './Landing';

const meta: Meta<typeof Landing> = {
  title: 'Landing/Landing',
  component: Landing,
  parameters: { layout: 'fullscreen' },
};
export default meta;
type Story = StoryObj<typeof Landing>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(canvas.getByRole('heading', { level: 1, name: 'Your table, on your own machine' })).toBeInTheDocument();
    await expect(canvas.getByRole('region', { name: 'What is planned' })).toBeInTheDocument();
  },
};

/** For a visitor to the hosted service: the way in is signing in. */
export const SignIn: Story = {
  args: { start: { label: 'Sign in to start', href: '/user' } },
  play: async ({ canvasElement }) => {
    const links = within(canvasElement).getAllByRole('link', { name: 'Sign in to start' });
    await expect(links[0]).toHaveAttribute('href', '/user');
  },
};

/** The landing page at phone width: the header folds into its menu. */
export const Phone: Story = {
  globals: { viewport: { value: 'mobile1' } },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByText('Menu')).toBeInTheDocument();
  },
};
