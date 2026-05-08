    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, x5, 1            # x5 += 1 unconditionally
    andi    x7, x5, 1            # x7 = x5 & 1 (parity bit)
    beqz    x7, skip             # if x5 even, skip the x6 increment
    addi    x6, x6, 1            # else (x5 odd): x6 += 1
skip:
    addi    x8, x0, 16
    blt     x5, x8, _start       # while x5 < 16
    ebreak
    .size   _start, .-_start
