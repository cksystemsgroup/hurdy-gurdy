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
import {VisionSlide} from './VisionSlide';
import type {SlideProps} from './types';

export const SLIDES: Record<string, React.FC<SlideProps>> = {
  slide01: TitleSlide,
  slide02: VisionSlide,
  slide03: ProblemSlide,
  slide04: SquareSlide,
  slide05: GradesSlide,
  slide06: RoutesSlide,
  slide07: RegistrySlide,
  slide08: ExperimentSlide,
  slide09: EvidenceSlide,
  slide10: NameSlide,
};
