import React from 'react';
import {EvidenceSlide} from './EvidenceSlide';
import {ExperimentSlide} from './ExperimentSlide';
import {GradesSlide} from './GradesSlide';
import {NameSlide} from './NameSlide';
import {ProblemSlide} from './ProblemSlide';
import {RegistrySlide} from './RegistrySlide';
import {RoutesSlide} from './RoutesSlide';
import {SquareSlide} from './SquareSlide';
import {TitleSlide} from './TitleSlide';
import type {SlideProps} from './types';

export const SLIDES: Record<string, React.FC<SlideProps>> = {
  slide01: TitleSlide,
  slide02: ProblemSlide,
  slide03: SquareSlide,
  slide04: GradesSlide,
  slide05: RoutesSlide,
  slide06: RegistrySlide,
  slide07: ExperimentSlide,
  slide08: EvidenceSlide,
  slide09: NameSlide,
};
