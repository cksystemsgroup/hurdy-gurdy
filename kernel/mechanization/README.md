# Mechanization — the kernel's proved properties (KERNEL.md §9)

The standing obligation: a Lean development, grown beside the code,
for the kernel's load-bearing properties —

1. the result order (`results.key`) is a strict partial order;
2. best-per-question is monotone under log append (the ratchet);
3. once settled, always settled (the frontier never re-opens);
4. per question, the gap never grows and grades only move up the
   ladder;
5. the trust meet is well-defined: every evidence item's residual
   trust is exactly the lineage meet over its gap segment plus its
   judge.

Nothing here yet: the development starts when the first campaign has
given the definitions something to hold still against. This file is
the obligation made visible, so the layout never overstates.
