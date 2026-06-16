// 011X-c-byteswap-oN family: same C source, four gcc -O levels.
//
// Reverse the byte order of a 64-bit value via shift/mask/or. The
// loop body is bitvector-heavy (8 shifts, 8 masks, 8 or-into-acc
// per iteration on the unrolled scheme; the loop form below packs
// that into 8 iterations of one shift/mask/shift/or each).
//
// Tests engine differentiation on bvshift / bvor / bvand intensive
// code, with -O level varying how much of the loop survives. -O0
// keeps the 8-iter loop explicit; -O2+ may unroll it; -O3 may even
// recognise the byte-swap idiom and emit a single instruction
// (RV64 doesn't have one, but gcc may still rewrite the structure).

extern void trap(void) ;

int main(void) {
    volatile unsigned long x = 0xDEADBEEFCAFEBABEUL;  // volatile blocks folding
    unsigned long y = 0;
    for (int i = 0; i < 8; i++) {
        unsigned long b = (x >> (i * 8)) & 0xffUL;     // extract byte i
        y |= b << ((7 - i) * 8);                        // place at position 7-i
    }
    // 0xDEADBEEFCAFEBABE byte-reversed = 0xBEBAFECAEFBEADDE
    if (y != 0xBEBAFECAEFBEADDEUL) trap();
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
