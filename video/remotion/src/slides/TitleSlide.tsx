import React from 'react';
import {COLORS, FONTS, PAPER_SUBTITLE, PAPER_TITLE, REPO_URL} from '../theme';
import {Reveal, SlideShell} from '../ui';
import type {SlideProps} from './types';

export const TitleSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell index={index} total={total}>
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        textAlign: 'center',
      }}
    >
      <Reveal delay={4}>
        <div
          style={{
            fontSize: 34,
            letterSpacing: 6,
            textTransform: 'uppercase',
            color: COLORS.accent,
            fontWeight: 'bold',
            marginBottom: 22,
          }}
        >
          hurdy-gurdy
        </div>
      </Reveal>
      <Reveal delay={10}>
        <h1
          style={{
            fontSize: 96,
            lineHeight: 1.12,
            margin: 0,
            marginBottom: 30,
            fontWeight: 'bold',
            color: COLORS.text,
          }}
        >
          {PAPER_TITLE}
        </h1>
      </Reveal>
      <Reveal delay={18}>
        <div style={{fontSize: 48, color: COLORS.dim, marginBottom: 70}}>
          {PAPER_SUBTITLE}
        </div>
      </Reveal>
      <Reveal delay={26}>
        <div style={{fontSize: 36, color: COLORS.body}}>
          Christoph Kirsch{' '}
          <span style={{color: COLORS.faint}}>
            · University of Salzburg · Czech Technical University
          </span>
        </div>
      </Reveal>
      <Reveal delay={32}>
        <div
          style={{
            fontFamily: FONTS.mono,
            fontSize: 32,
            color: COLORS.accent,
            marginTop: 28,
          }}
        >
          {REPO_URL}
        </div>
      </Reveal>
    </div>
  </SlideShell>
);
