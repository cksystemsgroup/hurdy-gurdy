// 0010-c-byte-load-signedness: lowering-sensitive — LDRSB vs LDRB
// at -O0.
//
// In C, a `char` value of 0xFF read through a `signed char *` is
// -1 (sign-extended on widening); read through an `unsigned char
// *` it's 255 (zero-extended). The compiler emits LDRSB (sign-
// extending byte load) vs LDRB (zero-extending byte load); both
// instructions read the same memory but produce different
// register values.
//
// SCHEMA.md §5 (instruction lowering) makes the sign vs zero
// extension explicit; this is the AArch64 analogue of the RV64
// lb vs lbu surface.
//
// Port of riscv-btor2 0120-c-byte-load-signedness; RV64 lb/lbu
// become AArch64 LDRSB/LDRB — same observable results.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    volatile signed char   sc = (signed char)0xFF;    // -1
    volatile unsigned char uc = (unsigned char)0xFF;  // 255

    int s_widened = sc;                                // sign-ext via LDRSB → -1
    int u_widened = uc;                                // zero-ext via LDRB  → 255

    if (s_widened != -1)  trap();
    if (u_widened != 255) trap();
    __asm__ volatile ("svc #0");
}

void trap(void) {
    __asm__ volatile ("brk #0");
    __builtin_unreachable();
}
