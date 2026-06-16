// 0121-c-mulw-truncation: lowering-sensitive — 32-bit multiply
// truncation at -O0.
//
// In C, `int * int` evaluates as int — the standard's "usual
// arithmetic conversions" don't widen to long for the
// multiplication. On RV64 this lowers to MULW (32-bit multiply
// of low 32 bits, sign-extend result to 64). For 0x10000 *
// 0x10000 = 0x100000000, the low 32 bits are 0 (the high bit of
// the result that would overflow into bit 32+ is dropped). MULW
// then sign-extends 0 to 64 → 0.
//
// A C reader who thinks "small * small can't overflow" misses
// that the *type* of the operands determines the lowering, not
// the values. The BTOR2 lowering encodes the bvmul + low-32 +
// sign-extend explicitly.

extern void trap(void) ;

int main(void) {
    volatile int x = 0x10000;       // 65536
    volatile int y = 0x10000;       // 65536
    int product = x * y;             // RV64 MULW: low-32 of 0x100000000 = 0
    long widened = product;          // sign-ext: still 0
    if (widened != 0) trap();        // assertion holds (overflow truncates)
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
