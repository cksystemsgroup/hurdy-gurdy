// 0116-c-divu-sentinel: lowering-sensitive — unsigned div-by-zero
// at -O0.
//
// In C, integer division by zero is undefined behaviour. A C
// reader might say "this program is UB, the LLM should refuse to
// reason about it." On RV64 the picture is concrete: SCHEMA.md §13
// (the lowering-sensitive cases SCOPE.md cites) and the rotor
// lineage spell out that DIVU returns a sentinel of all-ones
// on division by zero — there is no trap, no hardware fault.
//
// Two compounding lowering surfaces are visible here:
//
// 1. divuw on (42, 0) returns the 32-bit sentinel 0xFFFFFFFF
//    (SCHEMA.md §5 — DIVU sentinel).
// 2. The W-suffix instruction sign-extends the 32-bit result to
//    64 bits, so the destination register holds
//    0xFFFFFFFFFFFFFFFF momentarily.
// 3. C's unsigned-int → unsigned-long widening is *value-
//    preserving* (zero-extend per the C standard), so gcc emits
//    a zero-extension after the divuw, masking the upper 32 bits
//    to zero. The final value of z is 0x00000000FFFFFFFF.
//
// A C reader who only sees the source-level "z = q" might trust
// the C-language zero-extension and predict z = 0xFFFFFFFFUL —
// that is correct. A reader who only sees the RV64 instruction
// stream (divuw + register state) might predict z =
// 0xFFFFFFFFFFFFFFFFUL — that's wrong because gcc adds the
// zero-extension shim to honour C semantics. The BTOR2 lowering
// makes BOTH layers explicit.
//
// The trap is provably unreachable iff the lowering correctly
// models BOTH the DIVU sentinel and the gcc-emitted
// zero-extension shim.

extern void trap(void) ;

int main(void) {
    volatile unsigned int x = 42;
    volatile unsigned int y = 0;
    unsigned int q = x / y;           // RV64 divuw → 0xFFFFFFFF (sentinel)
    unsigned long z = q;              // gcc emits zero-extension shim
                                      // → z = 0x00000000FFFFFFFF
    if (z != 0xFFFFFFFFUL) trap();
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
