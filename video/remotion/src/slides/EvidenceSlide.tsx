import React from 'react';
import {COLORS} from '../theme';
import {BulletList, SlideShell, Strong} from '../ui';
import type {SlideProps} from './types';

export const EvidenceSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The evidence"
    title="What the gate caught"
    index={index}
    total={total}
  >
    <BulletList
      stagger={14}
      items={[
        <>
          Measured <Strong>per-construct coverage</Strong>: covered ∧ faithful,
          against spec inventories and public benchmark suites
        </>,
        <>
          <Strong>Branch agreement</Strong> along the dual RISC-V and AArch64
          routes, with machine-derived ground truth
        </>,
        <>
          <Strong>Certified unreachability</Strong> re-validated by a formally
          verified checker
        </>,
        <>
          Real defects caught — including one in the certificate pipeline’s{' '}
          <strong style={{color: COLORS.accent}}>own checker adapter</strong>{' '}
          and three in its{' '}
          <strong style={{color: COLORS.accent}}>
            own measuring instruments
          </strong>
        </>,
      ]}
    />
  </SlideShell>
);
