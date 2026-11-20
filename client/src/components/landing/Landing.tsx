// SPDX-License-Identifier: AGPL-3.0-or-later
import { CtaBand, FaqList, FeatureCard, Hero, Section, SiteFooter, SiteHeader } from '@zephyrex/marketing';
import type { ReactElement } from 'react';
import { CLOSING, FAQS, FOOTER, HERO, NAV, PLANNED, START, TODAY } from '~/content/marketing';
import { APP_NAME } from '~/zephyrex.config';

/** What the app is, for a visitor: what works today, what is planned, and the way in. */
export function Landing({ start = START }: { start?: { label: string; href: string } }): ReactElement {
  return (
    <div className='flex min-h-svh w-full min-w-0 flex-col'>
      <SiteHeader brand={APP_NAME} nav={NAV} cta={start} />
      <main className='mx-auto w-full min-w-0 max-w-5xl space-y-20 px-4 pb-12'>
        <Hero
          title={HERO.title}
          lead={HERO.lead}
          primary={start}
          secondary={{ label: 'What works today', href: '#today' }}
        />
        <Section id='today' title='What it does today' eyebrow='Today'>
          <div className='grid gap-4 sm:grid-cols-2'>
            {TODAY.map((feature) => (
              <FeatureCard key={feature.id} feature={feature} />
            ))}
          </div>
        </Section>
        <Section id='planned' title='What is planned' eyebrow='Planned'>
          <div className='grid gap-4 sm:grid-cols-2'>
            {PLANNED.map((feature) => (
              <FeatureCard key={feature.id} feature={feature} />
            ))}
          </div>
        </Section>
        <Section id='faq' title='Questions' eyebrow='FAQ'>
          <FaqList faqs={FAQS} />
        </Section>
        <CtaBand title={CLOSING.title} body={CLOSING.body} action={start} />
        <SiteFooter columns={FOOTER} note={`${APP_NAME} is open source under the AGPL.`} />
      </main>
    </div>
  );
}
