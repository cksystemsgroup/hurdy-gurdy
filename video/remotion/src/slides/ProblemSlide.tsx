import React from 'react';
import {COLORS} from '../theme';
import {BulletList, SlideShell, Strong} from '../ui';
import type {SlideProps} from './types';

export const ProblemSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The problem"
    title="Every translation is a place to be wrong"
    index={index}
    total={total}
  >
    <BulletList
      items={[
        <>
          A <Strong>C</Strong> reachability question becomes a bit-vector{' '}
          <Strong>model-checking</Strong> problem; a <Strong>Python</Strong>{' '}
          assertion becomes an <Strong>arithmetic query</Strong>
        </>,
        <>
          Classical answers: <Strong>prove the translator once</Strong>{' '}
          (certified compilation) or <Strong>validate each run</Strong>{' '}
          (translation validation)
        </>,
        <>
          Both are statements about a <Strong>single edge</Strong> — but in
          practice representations form a{' '}
          <strong style={{color: COLORS.accent}}>graph</strong>, with edges of{' '}
          <Strong>honestly different</Strong> trustworthiness
        </>,
      ]}
    />
  </SlideShell>
);
