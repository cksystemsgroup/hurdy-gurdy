// 0002-c-loopsum-o1: AArch64 bare-metal loop sum, compiled -O1.
// Same logic as 0001-c-loopsum-o0; only the compiler optimisation level differs.

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
