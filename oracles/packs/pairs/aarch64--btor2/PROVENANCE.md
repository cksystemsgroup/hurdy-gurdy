# `aarch64--btor2` — recorded testimony (anchor pack)

- **Source**: tag `era4-final`, `registry/pairs/aarch64--btor2/` (Era 4).
- **Kind at Era 4**: translation pair `aarch64` → `btor2`,
  direction exact, keeps halted, pc, sp, x0, x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12, x13, x14, x15, x16, x17, x18, x19, x20, x21, x22, x23, x24, x25, x26, x27, x28, x29, x30; lineage:
  hurdy-gurdy:aarch64-btor2-translator. Carried over from gurdy/pairs/aarch64_btor2/translate.py (v3; the direct A64 lowering, one instruction per cycle) — nzcv is not in keeps: the admitted btor2 entry's observable filter drops n*-symbols, so the flags square on the aarch64--sail hop instead.
- **Corpus**: 4 source programs, copied verbatim, on which the Era-4
  square closed (corpus: 4, controls:
  2).
- **Status**: testimony (`KERNEL.md` §6). A regenerated pair between
  the same languages cites this corpus as the programs its square
  must close on; the Era-3 translator at the tag may be run there to
  pin target-side observables as further vectors — never imported.
