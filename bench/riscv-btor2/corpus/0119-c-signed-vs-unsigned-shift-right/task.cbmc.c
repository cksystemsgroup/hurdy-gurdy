// 0119-c-signed-vs-unsigned-shift-right: lowering-sensitive —
// SRAW (arithmetic) vs SRLW (logical) right shift on identical
// bit patterns at -O0.
//
// In C, `x >> 2` for `x = -8` (signed) gives -2 (sign-extended);
// for the same bit pattern reinterpreted as unsigned (0xFFFFFFF8),
// `x >> 2` gives 0x3FFFFFFE (zero-fill). The C source LOOKS
// syntactically identical (`x >> n`); the compiler picks SRAW
// vs SRLW based on the operand's type.
//
// On RV64 these are different instructions emitted from the same
// C operator. The BTOR2 lowering encodes both as the right
// concatenation/sign-fill or zero-fill on the bvshr semantics.

extern void trap(void) ;

int main(void) {
    volatile int  s = -8;             // signed:   0xFFFFFFF8
    volatile unsigned int u = 0xFFFFFFF8U;  // same bits, unsigned

    int  s_shifted = s >> 2;          // SRAW: arithmetic, sign-fill → -2
    unsigned int u_shifted = u >> 2;  // SRLW: logical,   zero-fill → 0x3FFFFFFE

    if (s_shifted != -2)               trap();  // assertion holds
    if (u_shifted != 0x3FFFFFFEU)      trap();  // assertion holds
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
