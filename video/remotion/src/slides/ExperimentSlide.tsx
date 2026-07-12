import React from 'react';
import {COLORS} from '../theme';
import {BulletList, SlideShell, Strong} from '../ui';
import type {SlideProps} from './types';

export const ExperimentSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The experiment"
    title="Untrusted authors, in both directions"
    index={index}
    total={total}
  >
    <BulletList
      stagger={14}
      items={[
        <>
          <Strong>Every pair was written by an independent LLM agent</Strong>{' '}
          from a one-page brief, largely unsupervised — the architecture’s
          cross-checks are the only semantic gate
        </>,
        <>
          The intended <Strong>player</Strong> is also an LLM: it chooses
          questions and routes, but{' '}
          <strong style={{color: COLORS.accent}}>
            can take no unchecked step
          </strong>
        </>,
        <>
          The compositional core of the calculus is{' '}
          <Strong>mechanized in Lean&nbsp;4</Strong>
        </>,
        <span style={{color: COLORS.accent}}>
          <strong>Trust comes from the architecture, not from the author</strong>
        </span>,
      ]}
    />
  </SlideShell>
);
