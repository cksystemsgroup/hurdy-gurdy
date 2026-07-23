import React from 'react';
import {COLORS, PAPER_SUBTITLE, PAPER_TITLE, REPO_URL} from '../theme';
import {BulletList, Mono, Reveal, SlideShell, Strong} from '../ui';
import type {SlideProps} from './types';

export const NameSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="Why the name"
    title="The instrument and the player"
    index={index}
    total={total}
  >
    <Reveal delay={12}>
      <p style={{margin: 0, marginBottom: 26}}>
        A hurdy-gurdy’s player cranks a wheel; the mechanism turns each choice
        into sound <Strong>the same way, every time</Strong>.
      </p>
    </Reveal>
    <BulletList
      startDelay={24}
      items={[
        <>
          the <Strong>translator</Strong> is the keyboard — same key → same
          pitch
        </>,
        <>
          the <Strong>interpreters</Strong> are the wheel — they make the sound
          real
        </>,
        <>
          the <Strong>player</Strong> — an LLM, or you — decides what to ask
        </>,
      ]}
    />
    <Reveal delay={60}>
      <p style={{marginTop: 50, fontSize: 36, color: COLORS.dim}}>
        Paper:{' '}
        <strong style={{color: COLORS.text}}>
          “{PAPER_TITLE}: {PAPER_SUBTITLE}”
        </strong>{' '}
        (<Mono>arXiv:2607.14137</Mono> v2 — <Mono>paper/arxiv.pdf</Mono>, tag{' '}
        <Mono>arxiv.2</Mono>)
        <br />
        Code, evidence &amp; Lean mechanization:{' '}
        <Mono style={{color: COLORS.accent}}>{REPO_URL}</Mono>
      </p>
    </Reveal>
  </SlideShell>
);
