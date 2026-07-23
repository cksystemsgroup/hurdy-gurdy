import React from 'react';
import {COLORS, FONTS} from '../theme';
import {
  Accent,
  BulletList,
  DrawnPath,
  FadeG,
  PopGroup,
  SlideShell,
  Strong,
} from '../ui';
import type {SlideProps} from './types';

const Node: React.FC<{
  x: number;
  y: number;
  w: number;
  label: string;
  hub?: boolean;
}> = ({x, y, w, label, hub}) => (
  <>
    <rect
      x={x}
      y={y}
      width={w}
      height={90}
      rx={12}
      fill={hub ? COLORS.hub : COLORS.node}
      stroke={hub ? COLORS.accent : COLORS.stroke}
      strokeWidth={hub ? 3 : 2}
    />
    <text
      x={x + w / 2}
      y={y + 58}
      textAnchor="middle"
      fontSize={40}
      fill={COLORS.bright}
      fontFamily={FONTS.mono}
    >
      {label}
    </text>
  </>
);

/** The two directions: LLMs build the platform; LLMs play it. */
const BootstrapDiagram: React.FC = () => (
  <svg width={1338} height={361} viewBox="0 0 1520 410">
    <defs>
      <marker
        id="arrV"
        markerWidth={10}
        markerHeight={8}
        refX={9}
        refY={4}
        orient="auto"
      >
        <path d="M0,0 L10,4 L0,8 z" fill={COLORS.accent} />
      </marker>
    </defs>
    <PopGroup cx={300} cy={205} delay={8}>
      <Node x={140} y={160} w={320} label="LLMs" />
    </PopGroup>
    <PopGroup cx={1250} cy={205} delay={16}>
      <Node x={1060} y={160} w={380} label="hurdy-gurdy" hub />
    </PopGroup>
    {/* Reveals are paced to the ~48s narration: the arrows and bullets land
        as their sentences are spoken, not all in the first seconds. */}
    <DrawnPath
      d="M 470,160 C 660,70 860,70 1050,160"
      from={335}
      dur={24}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arrV)"
    />
    <FadeG from={347}>
      <text x={760} y={72} textAnchor="middle" fontSize={28} fill={COLORS.dim}>
        build it — untrusted authors, gated by the architecture’s cross-checks
      </text>
    </FadeG>
    <DrawnPath
      d="M 1050,250 C 860,340 660,340 470,250"
      from={614}
      dur={24}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arrV)"
    />
    <FadeG from={626}>
      <text x={760} y={358} textAnchor="middle" fontSize={28} fill={COLORS.dim}>
        play it — generate correct code through deterministic, graded, checked moves
      </text>
    </FadeG>
  </svg>
);

export const VisionSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The vision"
    title={
      <>
        <Accent>Bootstrapping LLMs</Accent> toward correctness
      </>
    }
    index={index}
    total={total}
  >
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
      <BootstrapDiagram />
    </div>
    <BulletList
      fontSize={34}
      startDelay={860}
      stagger={235}
      items={[
        <>
          A <Strong>two-directional experiment</Strong> in LLM-generated
          correctness: nearly all code is LLM-written — the human contribution
          is the <Strong>architecture</Strong>
        </>,
        <>
          The same gate is the <Strong>growth model</Strong>: anyone — LLM,
          agent, or human — lands a new pair by ordinary pull request,{' '}
          <strong style={{color: COLORS.accent}}>
            admitted by the architecture, not the author
          </strong>
        </>,
        <>
          <Strong>Two planes</Strong>, one registry —{' '}
          <strong style={{color: COLORS.accent}}>
            answers never write; growth never answers
          </strong>
        </>,
      ]}
    />
  </SlideShell>
);
