// 0124-c-call-arg-promotion: lowering-sensitive — sign extension
// at function-call boundary, -O0.
//
// In C, passing a `signed char` value to a function with `int`
// parameter triggers an implicit promotion: the char's value
// (-10 here, bit pattern 0xF6) is *sign-extended* to int (-10,
// bit pattern 0xFFFFFFF6). On RV64 the call ABI passes the int
// in a0 — gcc emits a sign-extending byte load + arithmetic at
// the call site to materialise -10 in a0's full 64 bits.
//
// A C reader who thinks "byte is byte" might predict 0xF6 in a0
// (i.e., +246 as int). The actual call gets -10. The BTOR2
// lowering encodes the sign-extension in the load + the arg-
// passing.

extern void trap(void) __attribute__((noreturn));

static int add100(int x) {
    return x + 100;
}

void _start(void) {
    volatile signed char c = -10;     // 0xF6
    int sum = add100(c);              // c sign-extends to -10 at call boundary
    if (sum != 90) trap();            // -10 + 100 = 90 (NOT 246+100=346)
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
