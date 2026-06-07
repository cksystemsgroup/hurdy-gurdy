// 0006-c-udiv-by-zero: lowering-sensitive — unsigned div-by-zero
// at -O0.
//
// In C, integer division by zero is undefined behaviour. A C
// reader might say "this program is UB, the LLM should refuse to
// reason about it." On AArch64 the picture is concrete: UDIV
// returns 0 on division by zero — there is no trap, no hardware
// fault (SCHEMA.md §5, §14 AArch64-vs-RV64 divergence).
//
// AArch64 UDIV diverges from RV64 DIVU here: RV64 returns the
// all-ones sentinel (0xFFFFFFFF for W-suffix), whereas AArch64
// UDIV always returns 0 for any division by zero.
//
// The lowering surface:
// 1. UDIV W on (42, 0) returns 0 (not a sentinel).
// 2. C's unsigned-int → unsigned-long widening zero-extends: z = 0.
// 3. The trap condition checks z != 0, which is false → unreachable.
//
// A C reader who reasons from UB alone cannot predict the value;
// the BTOR2 lowering makes the AArch64 UDIV-by-zero semantic
// explicit. The trap is provably unreachable iff the lowering
// correctly models UDIV-by-zero → 0.
//
// Port of riscv-btor2 0116-c-divu-sentinel; the assertion is
// adapted because AArch64 returns 0, not the RV64 all-ones sentinel.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile unsigned int x = 42;
    volatile unsigned int y = 0;
    unsigned int q = x / y;           // AArch64 UDIV W-reg → 0 (div-by-zero)
    unsigned long z = q;              // zero-extend: z = 0
    if (z != 0UL) trap();             // assertion holds (z == 0)
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
