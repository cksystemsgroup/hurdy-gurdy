import React from 'react';
import {COLORS} from '../theme';
import {BulletList, Reveal, SlideShell} from '../ui';
import type {SlideProps} from './types';

const Hub: React.FC<{
  name: string;
  tagline: string;
  items: React.ReactNode[];
  startDelay: number;
}> = ({name, tagline, items, startDelay}) => (
  <div style={{flex: 1}}>
    <Reveal delay={startDelay}>
      <p style={{margin: 0, marginBottom: 26}}>
        <strong style={{color: COLORS.accent}}>{name}</strong> — {tagline}
      </p>
    </Reveal>
    <BulletList items={items} fontSize={36} startDelay={startDelay + 8} />
  </div>
);

export const RegistrySlide: React.FC<SlideProps> = ({index, total}) => (
  <SlideShell
    kicker="The registry"
    title="13 languages, 15 pairs, two hubs"
    index={index}
    total={total}
  >
    <div style={{display: 'flex', gap: 70}}>
      <Hub
        name="BTOR2 hub"
        tagline="bit-level model checking"
        startDelay={12}
        items={[
          <>
            C → RISC-V → BTOR2{' '}
            <span style={{color: COLORS.faint}}>(the spine)</span>
          </>,
          <>AArch64, WebAssembly, eBPF, EVM</>,
          <>
            dual routes via SAIL for RISC-V <em>and</em> AArch64
          </>,
          <>
            two abstraction endo-pairs{' '}
            <span style={{color: COLORS.faint}}>(loops on the hub)</span>
          </>,
        ]}
      />
      <Hub
        name="SMT-LIB hub"
        tagline="theory-rich queries"
        startDelay={44}
        items={[
          <>chemical reaction networks</>,
          <>Python (a fragment)</>,
          <>BTOR2 → SMT-LIB bridge</>,
        ]}
      />
    </div>
  </SlideShell>
);
