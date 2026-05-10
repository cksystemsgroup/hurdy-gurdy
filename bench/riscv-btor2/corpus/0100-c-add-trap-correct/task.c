// 0100-c-add-trap-correct: the C analogue of 0007-simple-add-baseline.
//
// Compute c = a + b with a=5, b=7, and trap if c != 12. The assertion
// always holds (c is always 12), so the trap is unreachable. This is
// the v0.4 C-corpus prototype that validates the _compile_c.py
// auto-spec-gen pipeline end-to-end.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    int a = 5;
    int b = 7;
    int c = a + b;
    if (c != 12) trap();
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
