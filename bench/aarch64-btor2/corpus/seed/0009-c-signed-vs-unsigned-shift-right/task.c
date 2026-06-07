// 0009-c-signed-vs-unsigned-shift-right: lowering-sensitive —
// ASR (arithmetic) vs LSR (logical) right shift on identical
// bit patterns at -O0.
//
// In C, `x >> 2` for `x = -8` (signed) gives -2 (sign-extended);
// for the same bit pattern reinterpreted as unsigned (0xFFFFFFF8),
// `x >> 2` gives 0x3FFFFFFE (zero-fill). The C source LOOKS
// syntactically identical (`x >> n`); the compiler picks ASR
// vs LSR based on the operand's type.
//
// On AArch64 these are different instructions emitted from the same
// C operator. The BTOR2 lowering encodes both via the correct
// bvashr (signed → sign-fill) or bvlshr (unsigned → zero-fill)
// semantics.
//
// Port of riscv-btor2 0119-c-signed-vs-unsigned-shift-right; RV64
// SRAW/SRLW become AArch64 ASR/LSR — same observable results.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int  s = -8;             // signed:   0xFFFFFFF8
    volatile unsigned int u = 0xFFFFFFF8U;  // same bits, unsigned

    int  s_shifted = s >> 2;          // ASR: arithmetic, sign-fill → -2
    unsigned int u_shifted = u >> 2;  // LSR: logical,   zero-fill → 0x3FFFFFFE

    if (s_shifted != -2)               trap();  // assertion holds
    if (u_shifted != 0x3FFFFFFEU)      trap();  // assertion holds
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
