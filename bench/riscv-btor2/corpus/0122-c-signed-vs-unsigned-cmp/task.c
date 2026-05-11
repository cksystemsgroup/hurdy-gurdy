// 0122-c-signed-vs-unsigned-cmp: lowering-sensitive — BLT vs
// BLTU at -O0.
//
// In C, comparing -1 (signed int) to 5 says "-1 < 5" (signed).
// Comparing the same bit pattern (0xFFFFFFFF) reinterpreted as
// unsigned says "0xFFFFFFFF > 5" (unsigned). The C source
// operator `<` is the same; the compiler picks BLT vs BLTU
// based on the operand types.
//
// SCOPE.md §4.2 cites the BGEU vs BGE distinction as a
// canonical lowering surface (hand-written 0013-bgeu-vs-bge).
// This is the C-source analogue: the same `<` operator dispatches
// to two different RV64 instructions on signed vs unsigned types.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int  s = -1;             // signed:   -1
    volatile unsigned int u = (unsigned int)-1;  // same bits, unsigned: 0xFFFFFFFF

    int s_lt = (s < 5);                // BLT:  -1 < 5  → 1 (true)
    int u_lt = (u < 5U);               // BLTU: 0xFFFFFFFF < 5 → 0 (false)

    if (s_lt != 1) trap();             // signed comparison: -1 IS less than 5
    if (u_lt != 0) trap();             // unsigned: 0xFFFFFFFF is NOT less than 5
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
