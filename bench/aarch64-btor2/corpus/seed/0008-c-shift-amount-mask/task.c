// 0008-c-shift-amount-mask: lowering-sensitive — shift amount
// outside [0, width) at -O0.
//
// In C, `x << n` where n is >= the width of x in bits or n is
// negative is undefined behaviour. A C reader might say "n=64
// on a 64-bit value, can't reason."
//
// On AArch64, LSL (register shift) takes a register operand for
// the shift amount and masks it to the low 6 bits before shifting
// (SCHEMA.md §5: shift-amount masking to 6 bits for 64-bit
// operands). 64 & 0x3f = 0, so `x << 64` becomes `x << 0` = `x`.
// The lowering encodes the bvand-mask explicitly.
//
// The trap is provably unreachable iff the lowering correctly
// models the shift-amount mask.
//
// Port of riscv-btor2 0118-c-shift-amount-mask; same behaviour
// (AArch64 LSL and RV64 SLL both mask shift amounts to 6 bits).

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile unsigned long x = 1;
    volatile int n = 64;            // shift amount; UB in C, masked to 0 on AArch64
    unsigned long y = x << n;       // AArch64: x << (64 & 0x3f) = x << 0 = x = 1
    if (y != 1) trap();             // assertion holds
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
