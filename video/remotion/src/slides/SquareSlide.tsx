import React from 'react';
import {COLORS, FONTS} from '../theme';
import {Accent, DrawnLine, FadeG, PopGroup, Reveal, SlideShell} from '../ui';
import type {SlideProps} from './types';

const Node: React.FC<{x: number; y: number; label: string}> = ({x, y, label}) => (
  <>
    <rect
      x={x}
      y={y}
      width={300}
      height={90}
      rx={12}
      fill={COLORS.node}
      stroke={COLORS.stroke}
      strokeWidth={2}
    />
    <text
      x={x + 150}
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

/** The commuting square, the paper's central diagram — drawn on over ~5s. */
const SquareDiagram: React.FC = () => (
  <svg width={1160} height={480} viewBox="0 0 1280 530">
    <defs>
      <marker
        id="arr"
        markerWidth={10}
        markerHeight={8}
        refX={9}
        refY={4}
        orient="auto"
      >
        <path d="M0,0 L10,4 L0,8 z" fill={COLORS.accent} />
      </marker>
    </defs>
    <PopGroup cx={210} cy={85} delay={8}>
      <Node x={60} y={40} label="source" />
    </PopGroup>
    <PopGroup cx={1070} cy={85} delay={16}>
      <Node x={920} y={40} label="target" />
    </PopGroup>
    <PopGroup cx={210} cy={445} delay={24}>
      <Node x={60} y={400} label="source'" />
    </PopGroup>
    <PopGroup cx={1070} cy={445} delay={32}>
      <Node x={920} y={400} label="target'" />
    </PopGroup>
    <DrawnLine
      x1={380}
      y1={85}
      x2={900}
      y2={85}
      from={42}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arr)"
    />
    <DrawnLine
      x1={210}
      y1={150}
      x2={210}
      y2={380}
      from={62}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arr)"
    />
    <DrawnLine
      x1={1070}
      y1={150}
      x2={1070}
      y2={380}
      from={62}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arr)"
    />
    <DrawnLine
      x1={900}
      y1={445}
      x2={380}
      y2={445}
      from={84}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arr)"
    />
    <FadeG from={46}>
      <text x={640} y={55} textAnchor="middle" fontSize={32} fill={COLORS.dim} fontFamily={FONTS.mono}>
        translate&nbsp;&nbsp;T
      </text>
    </FadeG>
    <FadeG from={66}>
      <text x={245} y={275} fontSize={32} fill={COLORS.dim} fontFamily={FONTS.mono}>
        interpret&nbsp;&nbsp;Iₛ
      </text>
      <text x={1035} y={275} textAnchor="end" fontSize={32} fill={COLORS.dim} fontFamily={FONTS.mono}>
        interpret&nbsp;&nbsp;Iₜ
      </text>
    </FadeG>
    <FadeG from={88}>
      <text x={640} y={510} textAnchor="middle" fontSize={32} fill={COLORS.dim} fontFamily={FONTS.mono}>
        carry back&nbsp;&nbsp;L
      </text>
    </FadeG>
  </svg>
);

export const SquareSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The unit"
    title={
      <>
        The pair is a <Accent>commuting square</Accent>
      </>
    }
    index={index}
    total={total}
  >
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
      <SquareDiagram />
    </div>
    <Reveal delay={104}>
      <div
        style={{
          fontFamily: FONTS.mono,
          textAlign: 'center',
          fontSize: 46,
          color: COLORS.accent,
          marginTop: 24,
        }}
      >
        Iₛ(p) ≡<sub>π</sub> L( Iₜ( T(p) ) )
      </div>
    </Reveal>
    {/* The directional refinement lands with its narration sentence (~41s). */}
    <Reveal delay={1245}>
      <div
        style={{
          textAlign: 'center',
          fontSize: 30,
          color: COLORS.dim,
          marginTop: 18,
        }}
      >
        directional: ≡<sub>π</sub> may weaken to ⊑<sub>π</sub> —
        over-approximation with a declared direction; exact is the special case
      </div>
    </Reveal>
  </SlideShell>
);
