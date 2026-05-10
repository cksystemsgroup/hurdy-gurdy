// 0101-c-add-trap-bug: deliberate-bug counterpart to 0100.
//
// Same shape as 0100, but the assertion is *reversed*: the program
// traps when c == 12 (which is always true). The trap is therefore
// always reached. Validates the auto-spec-gen pipeline on a
// `reachable`-verdict task and exercises the witness fingerprint
// path on a C-derived task.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    int a = 5;
    int b = 7;
    int c = a + b;
    if (c == 12) trap();
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
