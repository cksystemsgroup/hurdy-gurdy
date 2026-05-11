// 0120-c-byte-load-signedness: lowering-sensitive — `lb` vs `lbu`
// at -O0.
//
// In C, a `char` value of 0xFF read through a `signed char *` is
// -1 (sign-extended on widening); read through an `unsigned char
// *` it's 255 (zero-extended). The compiler emits `lb` (sign-
// extending byte load) vs `lbu` (zero-extending byte load); both
// instructions read the same memory but produce different
// 64-bit register values.
//
// SCHEMA.md §5 (instruction lowering) makes the sign vs zero
// extension explicit; SCOPE.md §4.2's "lbu vs lb" entry calls
// this out as a hand-written corpus surface (0005-lbu-vs-lb).
// This is the C-source analogue.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile signed char   sc = (signed char)0xFF;    // -1
    volatile unsigned char uc = (unsigned char)0xFF;  // 255

    int s_widened = sc;                                // sign-ext via lb  → -1
    int u_widened = uc;                                // zero-ext via lbu → 255

    if (s_widened != -1)  trap();
    if (u_widened != 255) trap();
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
