import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {BACKGROUND, COLORS, FONTS, REPO_URL} from './theme';

export const Accent: React.FC<{children: React.ReactNode}> = ({children}) => (
  <span style={{color: COLORS.accent}}>{children}</span>
);

export const Strong: React.FC<{children: React.ReactNode}> = ({children}) => (
  <strong style={{color: COLORS.bright}}>{children}</strong>
);

export const Mono: React.FC<{
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({children, style}) => (
  <span style={{fontFamily: FONTS.mono, ...style}}>{children}</span>
);

/** Fade-and-rise entrance, springing in `delay` frames after the slide starts. */
export const Reveal: React.FC<{
  delay?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({delay = 0, children, style}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = spring({
    frame: frame - delay,
    fps,
    config: {damping: 200},
    durationInFrames: 22,
  });
  return (
    <div
      style={{
        opacity: t,
        transform: `translateY(${(1 - t) * 30}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const BulletList: React.FC<{
  items: React.ReactNode[];
  fontSize?: number;
  startDelay?: number;
  stagger?: number;
}> = ({items, fontSize = 40, startDelay = 14, stagger = 10}) => (
  <ul style={{listStyle: 'none', margin: 0, padding: 0}}>
    {items.map((item, i) => (
      <li key={i} style={{marginBottom: 26}}>
        <Reveal delay={startDelay + i * stagger}>
          <div style={{position: 'relative', paddingLeft: 44, fontSize, lineHeight: 1.5}}>
            <span style={{position: 'absolute', left: 0, color: COLORS.accent}}>
              {'▸'}
            </span>
            {item}
          </div>
        </Reveal>
      </li>
    ))}
  </ul>
);

export const SlideShell: React.FC<{
  kicker?: string;
  title?: React.ReactNode;
  index: number;
  total: number;
  children: React.ReactNode;
}> = ({kicker, title, index, total, children}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill
      style={{
        background: BACKGROUND,
        color: COLORS.text,
        fontFamily: FONTS.sans,
        padding: '90px 120px 70px',
        display: 'flex',
        flexDirection: 'column',
        opacity,
      }}
    >
      {kicker ? (
        <>
          <Reveal delay={2}>
            <div
              style={{
                fontSize: 26,
                letterSpacing: 6,
                textTransform: 'uppercase',
                color: COLORS.accent,
                marginBottom: 22,
                fontWeight: 'bold',
              }}
            >
              {kicker}
            </div>
          </Reveal>
          <Reveal delay={6}>
            <h1
              style={{
                fontSize: 74,
                lineHeight: 1.12,
                margin: 0,
                marginBottom: 46,
                fontWeight: 'bold',
              }}
            >
              {title}
            </h1>
          </Reveal>
        </>
      ) : null}
      <div style={{flex: 1, fontSize: 40, lineHeight: 1.5, color: COLORS.body}}>
        {children}
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          fontSize: 26,
          color: COLORS.faint,
          fontFamily: FONTS.mono,
        }}
      >
        <span>{REPO_URL}</span>
        <span>
          {String(index).padStart(2, '0')} / {String(total).padStart(2, '0')}
        </span>
      </div>
    </AbsoluteFill>
  );
};

/** An SVG line that draws itself on between frames [from, from+dur]. */
export const DrawnLine: React.FC<{
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  from: number;
  dur?: number;
  stroke: string;
  strokeWidth: number;
  markerEnd?: string;
}> = ({x1, y1, x2, y2, from, dur = 18, stroke, strokeWidth, markerEnd}) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [from, from + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (t === 0) {
    return null;
  }
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x1 + (x2 - x1) * t}
      y2={y1 + (y2 - y1) * t}
      stroke={stroke}
      strokeWidth={strokeWidth}
      markerEnd={t === 1 ? markerEnd : undefined}
    />
  );
};

/** An SVG group fading in between frames [from, from+dur]. */
export const FadeG: React.FC<{
  from: number;
  dur?: number;
  children: React.ReactNode;
}> = ({from, dur = 14, children}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [from, from + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return <g opacity={opacity}>{children}</g>;
};

/** Pop-in wrapper for SVG node groups (scale about a given center). */
export const PopGroup: React.FC<{
  cx: number;
  cy: number;
  delay: number;
  children: React.ReactNode;
}> = ({cx, cy, delay, children}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = spring({
    frame: frame - delay,
    fps,
    config: {damping: 16, mass: 0.8},
    durationInFrames: 24,
  });
  return (
    <g
      opacity={Math.min(1, t * 2)}
      transform={`translate(${cx} ${cy}) scale(${0.6 + 0.4 * t}) translate(${-cx} ${-cy})`}
    >
      {children}
    </g>
  );
};
