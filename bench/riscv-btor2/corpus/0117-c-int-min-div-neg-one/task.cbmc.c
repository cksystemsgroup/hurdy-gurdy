// 0117-c-int-min-div-neg-one: lowering-sensitive — INT_MIN / -1 at
// -O0.
//
// Per the C standard, signed integer overflow is UB and INT_MIN /
// -1 is the canonical example: the mathematically correct
// quotient |INT_MIN| = 2^31 doesn't fit in a 32-bit signed
// integer. A C reader might say "this is UB, refuse to reason."
//
// On RV64, SCHEMA.md §13 / SCOPE.md §4.2 spell out the
// sentinel: signed DIV on (INT_MIN, -1) returns INT_MIN as the
// quotient (preserving the overflow rather than trapping). divw
// then sign-extends the 32-bit result to 64; C's signed-int →
// signed-long widening also sign-extends, so q lifted into long
// is INT_MIN extended = 0xFFFFFFFF80000000 = -2147483648L.
//
// The trap is provably unreachable iff the lowering correctly
// models the DIV-overflow sentinel.

extern void trap(void) ;

int main(void) {
    volatile int x = (int)0x80000000;        // INT_MIN
    volatile int y = -1;
    int q = x / y;                            // RV64 divw → INT_MIN sentinel
    long z = q;                               // sign-ext: -2147483648L
    if (z != -2147483648L) trap();            // assertion holds
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
