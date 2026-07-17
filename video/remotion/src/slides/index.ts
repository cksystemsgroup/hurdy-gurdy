import React from 'react';
import {EvidenceSlide} from './EvidenceSlide';
import {ExampleSlide} from './ExampleSlide';
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
  slide02: ExampleSlide,
  slide03: VisionSlide,
  slide04: ProblemSlide,
  slide05: SquareSlide,
  slide06: GradesSlide,
  slide07: RoutesSlide,
  slide08: RegistrySlide,
  slide09: ExperimentSlide,
  slide10: EvidenceSlide,
  slide11: NameSlide,
};
