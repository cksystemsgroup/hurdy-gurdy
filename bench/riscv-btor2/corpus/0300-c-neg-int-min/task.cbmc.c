// 0300-c-neg-int-min: lowering-sensitive — unary negation of INT_MIN at -O0.
//
// In C, the expression -x where x holds INT_MIN (0x80000000) is signed-
// integer-overflow UB: the mathematical result 2^31 does not fit in int.
// A C-level verifier that checks arithmetic overflow reports a violation.
//
// On RV64 gcc -O0 emits negw (subw rd, x0, rs): two's-complement 32-bit
// negation.  0 - 0x80000000 mod 2^32 = 0x80000000, which is INT_MIN again.
// The W-suffix instruction sign-extends to 64 bits, giving -2147483648L.
// The trap fires if z != INT_MIN — unreachable because the negw result IS
// INT_MIN.

extern void trap(void) ;

int main(void) {
    volatile int x = (int)0x80000000;  // INT_MIN
    int y = -x;                         // C UB: overflow; RV64 negw → INT_MIN
    long z = y;                         // sign-extend: -2147483648L
    if (z != -2147483648L) trap();
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
