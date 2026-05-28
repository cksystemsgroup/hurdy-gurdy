// 0001-c-loopsum-o0: AArch64 bare-metal loop sum.
// Same logic as riscv-btor2 0103-c-loopsum-o0; halt convention:
//   normal halt → svc #0, bad halt → brk #0 (distinct PCs).
//
// Sum 0+1+...+(n-1) where n=10 (volatile to prevent constant folding).
// Expected sum = 45. Trap if sum != 45 — assertion always holds, so
// trap() is unreachable.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile unsigned long n = 10;
    unsigned long sum = 0;
    for (unsigned long i = 0; i < n; i++) {
        sum += i;
    }
    if (sum != 45) trap();
    __asm__ volatile ("svc #0");
    __builtin_unreachable();
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
