// 0005-c-int-overflow: lowering-sensitive — signed integer overflow
// at -O0.
//
// A C reader thinking in C-standard terms reads
//
//     int y = x + 1;            // x is INT_MAX
//
// as undefined behaviour ("anything could happen"). gcc at -O0
// emits this faithfully as `add` on a W register (32-bit), which
// wraps two's-complement: INT_MAX + 1 = INT_MIN (= -2^31). The
// subsequent `int y -> long z` widening compiles to SXTW
// (sign-extend word to 64 bits), preserving the negative sign
// and giving z = -2147483648.
//
// The BTOR2 lowering makes both the 32-bit wraparound and the
// SXTW sign-extension explicit (SCHEMA.md §5 W-reg handling).
// A reader who only sees the C source might claim "UB, can't
// reason about it"; the bench's lowering forces the actual
// AArch64 behaviour into the analysis.
//
// Port of riscv-btor2 0115-c-int-overflow; RV64 addw+sign-ext
// becomes AArch64 ADD(W-reg)+SXTW — same observable result.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int x = 0x7FFFFFFF;     // INT_MAX
    int y = x + 1;                    // AArch64 ADD W-reg → 0x80000000 = INT_MIN
    long z = y;                       // SXTW: 0xFFFFFFFF80000000 = -2147483648L
    if (z != -2147483648L) trap();    // assertion holds
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
