// 0102-c-mul-chain-correct: C analogue of 0050-deep-mul-chain.
//
// Compute 2 * 3^9 = 39366 by 9 sequential multiplications and trap
// if the result is wrong. The assertion always holds. Pinned to
// bitwuzla via task.toml [c].engine — the engine_bench data on the
// hand-written 0050 says bitwuzla is ~11× faster on this shape, and
// the C-derived analogue should benefit from the same pin.

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    long x = 2;
    long m = 3;
    x *= m;  // 6
    x *= m;  // 18
    x *= m;  // 54
    x *= m;  // 162
    x *= m;  // 486
    x *= m;  // 1458
    x *= m;  // 4374
    x *= m;  // 13122
    x *= m;  // 39366
    if (x != 39366) trap();
    __asm__ volatile ("ebreak");
}

void trap(void) {
    __asm__ volatile ("ebreak");
    __builtin_unreachable();
}
