// 0007-c-int-min-div-neg-one: lowering-sensitive — INT_MIN / -1
// at -O0.
//
// Per the C standard, signed integer overflow is UB and INT_MIN /
// -1 is the canonical example: the mathematically correct
// quotient |INT_MIN| = 2^31 doesn't fit in a 32-bit signed
// integer. A C reader might say "this is UB, refuse to reason."
//
// On AArch64, SDIV truncates the result to the data size. For
// W-reg SDIV: the mathematical quotient 2^31 as 32 bits is
// 0x80000000 = INT_MIN (signed). SXTW then sign-extends to 64
// bits, giving z = 0xFFFFFFFF80000000 = -2147483648L.
//
// The result matches RV64's DIV-overflow sentinel (INT_MIN) but
// the mechanism differs: AArch64 uses truncation to data size
// rather than an explicit sentinel contract. The BTOR2 lowering
// makes the 32-bit truncation + SXTW chain explicit.
//
// Port of riscv-btor2 0117-c-int-min-div-neg-one; same observable
// result via a different ISA mechanism.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile int x = (int)0x80000000;        // INT_MIN
    volatile int y = -1;
    int q = x / y;                            // AArch64 SDIV W: truncate → INT_MIN
    long z = q;                               // SXTW: -2147483648L
    if (z != -2147483648L) trap();            // assertion holds
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
