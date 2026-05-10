// 010X-c-loopsum-oN family: same C source, four gcc -O levels.
//
// Sum 0 + 1 + ... + (n-1) where n=10 (volatile to prevent constant
// folding). Expected sum = 45. Trap if sum != 45 — assertion always
// holds, so the trap is unreachable.
//
// Purpose: demonstrate that the same .c file produces four
// distinct ELFs across gcc -O0 / -O1 / -O2 / -O3, each with a
// different BTOR2 trace shape but the same expected verdict.
// The cross-level engine_bench numbers reveal where each
// optimization level's BMC cost lands.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile unsigned long n = 10;   // volatile blocks compile-time folding
    unsigned long sum = 0;
    for (unsigned long i = 0; i < n; i++) {
        sum += i;
    }
    if (sum != 45) trap();           // 0+1+...+9 = 45
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
