// 0302-c-intmax-add-one: lowering-sensitive — signed overflow on INT_MAX + 1.
//
// C UB: adding 1 to INT_MAX (0x7FFFFFFF) overflows signed int.
// C11 §6.5 p5: "If an exceptional condition occurs during the evaluation of an
// expression (that is, if the result is not mathematically defined or not in
// the range of representable values for its type), the behavior is undefined."
//
// On RV64 gcc -O0, the compiler emits `addw a5, a5, 1` for `x + 1`.
// addw computes the 32-bit addition wrapping mod 2^32:
//   0x7FFFFFFF + 1 = 0x80000000.
// The W-suffix sign-extends to 64 bits: 0xFFFFFFFF80000000 = -2147483648L.
//
// The trap condition tests whether y equals INT_MIN (-2147483648).
// On actual RV64 hardware this is always true (two's-complement wrap),
// so trap is provably unreachable.
//
// A C-level verifier that treats signed overflow as UB will flag the
// addition and report reachable (false positive), because from its model
// the result is unspecified / can be anything, including values != INT_MIN.
// CBMC uses --signed-overflow-check for this; ESBMC's overflow model for
// addw determines whether it also fires.
//
// Distinguisher from 0115-c-int-overflow: that task used an anonymous
// constant expression. Here we use a `volatile int` variable to force
// a load at runtime, ensuring the compiler cannot constant-fold the
// overflow and the verifier must reason about a dynamic value.

#include <limits.h>

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int x = INT_MAX;       // volatile forces runtime load
    int y = x + 1;                  // C UB: INT_MAX+1 overflows; RV64 addw → -2147483648
    if (y != INT_MIN) trap();
    __asm__ volatile ("ebreak");    // normal halt
}

void trap(void) {
    __asm__ volatile ("ebreak");    // bad halt — distinct PC
    __builtin_unreachable();
}
