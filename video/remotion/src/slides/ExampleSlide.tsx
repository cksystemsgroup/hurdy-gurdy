import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {COLORS, FONTS} from '../theme';
import {Accent, DrawnLine, DrawnPath, FadeG, PopGroup, Reveal, SlideShell} from '../ui';
import type {SlideProps} from './types';

// Frame anchors, tuned to the narration beats of slide02.wav.
const BEATS = {
  card: 8, // "This tiny C program..."
  question: 315, // "Can the assertion ever fail?"
  compile: 475, // "a pinned C compiler translates..."
  translate: 611, // "a translator written from the instruction-set manual..."
  verdict: 895, // "unreachable, on every input"
  carryBack: 951, // "The answer is carried back to the C source line"
  certificate: 1024, // "...an independent checker re-validates"
  sail: 1186, // "a second way down ... through sail"
  agree: 1340, // "...and the two routes must agree"
  caption: 1395, // "One question, two independently built routes..."
};

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
      height={80}
      rx={12}
      fill={hub ? COLORS.hub : COLORS.node}
      stroke={hub ? COLORS.accent : COLORS.stroke}
      strokeWidth={hub ? 3 : 2}
    />
    <text
      x={x + w / 2}
      y={y + 52}
      textAnchor="middle"
      fontSize={36}
      fill={COLORS.bright}
      fontFamily={FONTS.mono}
    >
      {label}
    </text>
  </>
);

/** The example program; the assert line lights up when the answer lands. */
const CodeCard: React.FC = () => {
  const frame = useCurrentFrame();
  const comment = interpolate(frame, [BEATS.question, BEATS.question + 14], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const landed = interpolate(frame, [BEATS.carryBack + 8, BEATS.carryBack + 26], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const line: React.CSSProperties = {whiteSpace: 'pre', lineHeight: 1.8};
  return (
    <Reveal delay={BEATS.card}>
      <div
        style={{
          background: COLORS.node,
          border: `2px solid ${COLORS.stroke}`,
          borderRadius: 14,
          padding: '26px 34px 22px',
          fontFamily: FONTS.mono,
          fontSize: 31,
          color: COLORS.bright,
          width: 470,
        }}
      >
        <div style={{fontSize: 24, color: COLORS.faint, marginBottom: 16}}>tiny.c</div>
        <div style={line}>{'uint8_t x = input();'}</div>
        <div style={line}>{'uint8_t y = 2*x + 1;'}</div>
        <div
          style={{
            ...line,
            margin: '0 -18px',
            padding: '0 18px',
            borderRadius: 8,
            background: `rgba(212, 162, 78, ${landed * 0.16})`,
          }}
        >
          {'assert(y != 128);'}
          <span style={{color: COLORS.accent, opacity: comment}}>{'  // ever?'}</span>
        </div>
        <div style={{fontSize: 24, color: COLORS.accent, marginTop: 18, opacity: landed}}>
          ✓ unreachable — every input
        </div>
      </div>
    </Reveal>
  );
};

/** The two routes the example takes to BTOR2, and the answer coming home. */
const ExampleDiagram: React.FC = () => (
  <svg width={1120} height={600} viewBox="0 0 1120 600">
    <defs>
      <marker id="arrEx" markerWidth={10} markerHeight={8} refX={9} refY={4} orient="auto">
        <path d="M0,0 L10,4 L0,8 z" fill={COLORS.arrow} />
      </marker>
      <marker id="arrExGold" markerWidth={10} markerHeight={8} refX={9} refY={4} orient="auto">
        <path d="M0,0 L10,4 L0,8 z" fill={COLORS.accent} />
      </marker>
    </defs>

    <DrawnLine
      x1={4}
      y1={230}
      x2={140}
      y2={230}
      from={BEATS.compile}
      dur={12}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arrEx)"
    />
    <FadeG from={BEATS.compile + 4}>
      <text textAnchor="middle" fontSize={24} fill={COLORS.faint}>
        <tspan x={72} y={166}>pinned</tspan>
        <tspan x={72} y={196}>compiler</tspan>
      </text>
    </FadeG>
    <PopGroup cx={265} cy={230} delay={BEATS.compile + 10}>
      <Node x={150} y={190} w={230} label="RISC-V" />
    </PopGroup>

    <DrawnLine
      x1={390}
      y1={230}
      x2={610}
      y2={230}
      from={BEATS.translate}
      dur={12}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arrEx)"
    />
    <FadeG from={BEATS.translate + 4}>
      <text x={500} y={205} textAnchor="middle" fontSize={25} fill={COLORS.faint}>
        from the ISA manual
      </text>
    </FadeG>
    <PopGroup cx={735} cy={230} delay={BEATS.translate + 10}>
      <Node x={620} y={190} w={230} label="BTOR2" hub />
    </PopGroup>

    <DrawnLine
      x1={860}
      y1={230}
      x2={892}
      y2={230}
      from={BEATS.verdict}
      dur={8}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arrEx)"
    />
    <PopGroup cx={1009} cy={230} delay={BEATS.verdict + 6}>
      <rect
        x={900}
        y={190}
        width={218}
        height={80}
        rx={12}
        fill={COLORS.hub}
        stroke={COLORS.accent}
        strokeWidth={3}
      />
      <text
        x={1009}
        y={230}
        textAnchor="middle"
        fontSize={28}
        fill={COLORS.accent}
        fontFamily={FONTS.mono}
      >
        unreachable
      </text>
      <text x={1009} y={258} textAnchor="middle" fontSize={24} fill={COLORS.faint}>
        model checker
      </text>
    </PopGroup>
    <FadeG from={BEATS.certificate}>
      <text x={1009} y={305} textAnchor="middle" fontSize={24} fill={COLORS.faint}>
        certificate re-validated ✓
      </text>
    </FadeG>

    <DrawnPath
      d="M 675 182 C 580 60, 170 60, 12 150"
      from={BEATS.carryBack}
      dur={22}
      stroke={COLORS.accent}
      strokeWidth={4}
      markerEnd="url(#arrExGold)"
    />
    <FadeG from={BEATS.carryBack + 12}>
      <text x={390} y={48} textAnchor="middle" fontSize={26} fill={COLORS.accent}>
        the answer comes back to the source line
      </text>
    </FadeG>

    <PopGroup cx={485} cy={500} delay={BEATS.sail}>
      <Node x={390} y={460} w={190} label="SAIL" />
    </PopGroup>
    <DrawnLine
      x1={300}
      y1={275}
      x2={430}
      y2={455}
      from={BEATS.sail + 10}
      dur={12}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arrEx)"
    />
    <DrawnLine
      x1={590}
      y1={495}
      x2={700}
      y2={278}
      from={BEATS.sail + 24}
      dur={12}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arrEx)"
    />
    <FadeG from={BEATS.sail + 16}>
      <text x={485} y={575} textAnchor="middle" fontSize={25} fill={COLORS.faint}>
        the architecture&apos;s formal model
      </text>
    </FadeG>
    <FadeG from={BEATS.agree}>
      <text x={885} y={400} textAnchor="middle" fontSize={30} fill={COLORS.accent}>
        the two routes must agree ✓
      </text>
    </FadeG>
  </svg>
);

export const ExampleSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="How it's used"
    title={
      <>
        One question, <Accent>two routes</Accent>
      </>
    }
    index={index}
    total={total}
  >
    <div style={{display: 'flex', gap: 44, alignItems: 'center'}}>
      <CodeCard />
      <ExampleDiagram />
    </div>
    <Reveal delay={BEATS.caption}>
      <div
        style={{
          textAlign: 'center',
          fontSize: 33,
          color: COLORS.accent,
          marginTop: 4,
        }}
      >
        one question · two independent routes · one checked answer — keep this
        picture in mind
      </div>
    </Reveal>
  </SlideShell>
);
