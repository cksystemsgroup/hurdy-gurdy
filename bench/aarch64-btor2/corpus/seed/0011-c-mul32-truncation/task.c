// 0011-c-mul32-truncation: lowering-sensitive — 32-bit multiply
// truncation at -O0.
//
// In C, `int * int` evaluates as int — the standard's "usual
// arithmetic conversions" don't widen to long for the
// multiplication. On AArch64 this lowers to MUL Wd, Wn, Wm
// (W-register multiply: low 32 bits of the product). For
// 0x10000 * 0x10000 = 0x100000000, the low 32 bits are 0. SXTW
// then sign-extends 0 to 64 → 0.
//
// A C reader who thinks "small * small can't overflow" misses
// that the *type* of the operands determines the lowering, not
// the values. The BTOR2 lowering encodes the bvmul + low-32 +
// sign-extend explicitly.
//
// Port of riscv-btor2 0121-c-mulw-truncation; RV64 MULW (32-bit
// multiply + sign-extend) becomes AArch64 MUL Wd (W-reg multiply
// + zero-extend in register, SXTW for C widening) — same result.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int x = 0x10000;       // 65536
    volatile int y = 0x10000;       // 65536
    int product = x * y;             // AArch64 MUL W-reg: low-32 of 0x100000000 = 0
    long widened = product;          // SXTW: still 0
    if (widened != 0) trap();        // assertion holds (overflow truncates)
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
