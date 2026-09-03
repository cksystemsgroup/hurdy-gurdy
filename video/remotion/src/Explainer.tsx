import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import manifest from './narration.json';
import {SLIDES} from './slides';

const {fps, leadInSeconds, tailSeconds} = manifest;

export const slideDurationInFrames = (narrationSeconds: number): number =>
  Math.round((leadInSeconds + narrationSeconds + tailSeconds) * fps);

export const totalDurationInFrames = manifest.slides.reduce(
  (sum, s) => sum + slideDurationInFrames(s.seconds),
  0
);

export const Explainer: React.FC = () => {
  const total = manifest.slides.length;
  let from = 0;
  return (
    <AbsoluteFill style={{background: '#0a0c11'}}>
      {manifest.slides.map((s, i) => {
        const Slide = SLIDES[s.id];
        if (!Slide) {
          throw new Error(`no slide component registered for '${s.id}'`);
        }
        const dur = slideDurationInFrames(s.seconds);
        const seq = (
          <Sequence key={s.id} from={from} durationInFrames={dur}>
            <Slide index={i + 1} total={total} />
            <Sequence from={Math.round(leadInSeconds * fps)}>
              <Audio src={staticFile(`audio/${s.id}.wav`)} />
            </Sequence>
          </Sequence>
        );
        from += dur;
        return seq;
      })}
    </AbsoluteFill>
  );
};
