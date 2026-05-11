// 0115-c-int-overflow: lowering-sensitive — signed integer overflow
// at -O0.
//
// A C reader thinking in C-standard terms reads
//
//     int y = x + 1;            // x is INT_MAX
//
// as undefined behaviour ("anything could happen"). gcc at -O0
// emits this faithfully as `addw` on RV64, which computes on the
// low 32 bits and wraps two's-complement: INT_MAX + 1 = INT_MIN
// (= -2^31). The subsequent `int y -> long z` widening compiles
// to a sign-extension that preserves the negative sign, giving
// z = -2147483648.
//
// The BTOR2 lowering makes both the wraparound and the
// sign-extension explicit (SCHEMA.md §5 word-only sign extension).
// A reader who only sees the C source might claim "UB, can't
// reason about it"; the bench's lowering forces the actual RV64
// behaviour into the analysis.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int x = 0x7FFFFFFF;     // INT_MAX
    int y = x + 1;                    // RV64 addw → 0x80000000 = INT_MIN
    long z = y;                       // sign-extend: 0xFFFFFFFF80000000
    if (z != -2147483648L) trap();    // assertion holds
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
