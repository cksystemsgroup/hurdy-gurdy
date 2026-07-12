import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {COLORS, FONTS} from '../theme';
import {Reveal, SlideShell, Strong} from '../ui';
import type {SlideProps} from './types';

const GRADES: Array<[string, string]> = [
  ['predicted', 'derivable byte-for-byte from a written specification'],
  ['reproducible', 'not predictable, but pinned ⇒ identical bytes'],
  ['checked', 'validated against the source on every run'],
  ['proved', 'accompanied by a machine-checked commutation proof'],
  ['trusted', 'taken on faith — never shipped uncovered'],
];

const Row: React.FC<{grade: string; meaning: string; delay: number}> = ({
  grade,
  meaning,
  delay,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = spring({
    frame: frame - delay,
    fps,
    config: {damping: 200},
    durationInFrames: 22,
  });
  const cell = {
    textAlign: 'left' as const,
    padding: '16px 28px',
    borderBottom: `1px solid ${COLORS.strokeDim}`,
  };
  return (
    <tr style={{opacity: t, transform: `translateY(${(1 - t) * 20}px)`}}>
      <td style={{...cell, fontFamily: FONTS.mono, color: COLORS.bright}}>
        {grade}
      </td>
      <td style={{...cell, color: COLORS.body}}>{meaning}</td>
    </tr>
  );
};

export const GradesSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The grades"
    title="Determinism, then honest fidelity"
    index={index}
    total={total}
  >
    <Reveal delay={12}>
      <p style={{fontSize: 36, margin: 0, marginBottom: 26}}>
        Every function is <Strong>pure</Strong>: same input ⇒ byte-identical
        output. On top of that, each pair <Strong>declares</Strong> what it
        guarantees:
      </p>
    </Reveal>
    <table style={{borderCollapse: 'collapse', width: '100%', fontSize: 34}}>
      <thead>
        <tr>
          {['Grade', 'The translator’s output is…'].map((h) => (
            <th
              key={h}
              style={{
                textAlign: 'left',
                padding: '16px 28px',
                color: COLORS.accent,
                borderBottom: `2px solid ${COLORS.stroke}`,
                textTransform: 'uppercase',
                letterSpacing: 2,
                fontSize: 27,
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {GRADES.map(([grade, meaning], i) => (
          <Row key={grade} grade={grade} meaning={meaning} delay={22 + i * 10} />
        ))}
      </tbody>
    </table>
  </SlideShell>
);
