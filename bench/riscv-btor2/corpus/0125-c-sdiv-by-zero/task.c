// 0125-c-sdiv-by-zero: lowering-sensitive — signed division by zero at -O0.
//
// In C, division by zero is undefined behaviour regardless of sign. A
// C-level analyser treats the result of `x / 0` as non-deterministic
// ("anything could happen") and therefore reports that the subsequent
// equality check might fail, making `trap` reachable (false positive).
//
// On RV64, SCHEMA.md §13 specifies the sentinel-on-overflow contract for
// signed division: divw returns the dividend unchanged when the divisor is
// zero. For `42 / 0`, divw returns 42 — NOT -1.  Wait: the RISC-V ISA
// spec (§M extension) says for DIV by zero: quotient = -1 (all bits set),
// remainder = dividend. So divw(42, 0) = -1 (32-bit, sign-extended to
// 0xFFFFFFFFFFFFFFFF = -1L). The W-suffix sign-extends to 64 bits.
// C's signed int → long widening also sign-extends, giving z = -1L.
//
// The trap is provably unreachable iff the lowering correctly models
// divw's division-by-zero sentinel (−1).

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int x = 42;
    volatile int y = 0;
    int q = x / y;          // RV64 divw(42, 0) → -1 (all-ones sentinel)
    long z = q;             // sign-ext: 0xFFFFFFFFFFFFFFFF = -1L
    if (z != -1L) trap();   // assertion holds — unreachable
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
