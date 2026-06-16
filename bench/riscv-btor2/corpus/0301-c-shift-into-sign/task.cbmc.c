// 0301-c-shift-into-sign: lowering-sensitive — left-shift into sign bit at -O0.
//
// In C, the expression x << 31 where x holds 1 is signed-integer-overflow UB:
// the mathematical result 2^31 = 2147483648 is not representable in int.
// C11 §6.5.7 p4: "…the behavior is undefined" when the result cannot be
// represented in the result type.  Note: the shift AMOUNT 31 is valid
// (< 32 = bit width), so --shift-check alone does not flag this; only
// --signed-overflow-check catches the sign-bit overflow.
//
// On RV64 gcc -O0 emits slliw: 32-bit logical left shift.
// slliw rd, rs1, 31: (1 << 31) mod 2^32 = 0x80000000.
// The W-suffix sign-extends to 64 bits: 0xFFFFFFFF80000000 = -2147483648L.
//
// The BTOR2 lowering models slliw as (sll bv64, sign-extend(bv32)) then
// sign-extend back.  The two's-complement result -2147483648 matches
// the C programmer's expectation only when the lowering is RV64-faithful.
// A C-level verifier that checks signed overflow reports a violation even
// though the trap is provably unreachable on actual RV64 hardware.

extern void trap(void) ;

int main(void) {
    volatile int x = 1;
    int y = x << 31;          // C UB: result 2^31 > INT_MAX; RV64 slliw → 0x80000000
    long z = y;               // sign-extend: 0xFFFFFFFF80000000 = -2147483648L
    if (z != -2147483648L) trap();
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
