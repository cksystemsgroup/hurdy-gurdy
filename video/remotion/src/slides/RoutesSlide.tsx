import React from 'react';
import {COLORS, FONTS} from '../theme';
import {Accent, DrawnLine, FadeG, PopGroup, SlideShell} from '../ui';
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

/** The spine with its Sail branch. */
const RoutesDiagram: React.FC = () => (
  <svg width={1520} height={500} viewBox="0 0 1520 500">
    <defs>
      <marker
        id="arr2"
        markerWidth={10}
        markerHeight={8}
        refX={9}
        refY={4}
        orient="auto"
      >
        <path d="M0,0 L10,4 L0,8 z" fill={COLORS.arrow} />
      </marker>
    </defs>
    <PopGroup cx={105} cy={150} delay={6}>
      <Node x={40} y={110} w={130} label="C" />
    </PopGroup>
    <PopGroup cx={415} cy={150} delay={12}>
      <Node x={300} y={110} w={230} label="RISC-V" />
    </PopGroup>
    <PopGroup cx={885} cy={150} delay={18}>
      <Node x={770} y={110} w={230} label="BTOR2" hub />
    </PopGroup>
    <PopGroup cx={1315} cy={150} delay={24}>
      <Node x={1180} y={110} w={270} label="SMT-LIB" hub />
    </PopGroup>
    <PopGroup cx={625} cy={370} delay={54}>
      <Node x={530} y={330} w={190} label="SAIL" />
    </PopGroup>
    <FadeG from={14}>
      <text x={235} y={90} textAnchor="middle" fontSize={26} fill={COLORS.faint}>
        pinned
      </text>
    </FadeG>
    <FadeG from={20}>
      <text x={650} y={90} textAnchor="middle" fontSize={26} fill={COLORS.faint}>
        from the ISA manual
      </text>
    </FadeG>
    <FadeG from={26}>
      <text x={1090} y={90} textAnchor="middle" fontSize={26} fill={COLORS.faint}>
        bridge
      </text>
    </FadeG>
    <DrawnLine
      x1={180}
      y1={150}
      x2={290}
      y2={150}
      from={32}
      dur={10}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arr2)"
    />
    <DrawnLine
      x1={540}
      y1={150}
      x2={760}
      y2={150}
      from={40}
      dur={12}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arr2)"
    />
    <DrawnLine
      x1={1010}
      y1={150}
      x2={1170}
      y2={150}
      from={48}
      dur={10}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arr2)"
    />
    <DrawnLine
      x1={440}
      y1={195}
      x2={570}
      y2={322}
      from={62}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arr2)"
    />
    <DrawnLine
      x1={700}
      y1={325}
      x2={830}
      y2={198}
      from={74}
      stroke={COLORS.arrow}
      strokeWidth={4}
      markerEnd="url(#arr2)"
    />
    <FadeG from={60}>
      <text x={420} y={290} textAnchor="end" fontSize={26} fill={COLORS.faint}>
        from the formal model
      </text>
    </FadeG>
    <FadeG from={78}>
      <text x={790} y={290} fontSize={26} fill={COLORS.faint}>
        independent route
      </text>
    </FadeG>
    <FadeG from={94} dur={18}>
      <text x={760} y={470} textAnchor="middle" fontSize={34} fill={COLORS.accent}>
        two independent routes to the same hub → agreement corroborates both
      </text>
    </FadeG>
  </svg>
);

export const RoutesSlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="Composition"
    title={
      <>
        Routes compose — and <Accent>branch</Accent>
      </>
    }
    index={index}
    total={total}
  >
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center'}}>
      <RoutesDiagram />
    </div>
  </SlideShell>
);
