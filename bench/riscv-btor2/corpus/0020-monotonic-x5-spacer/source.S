    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, x5, 1            # x5 += 1 (x5 starts at 0 via RegisterInit)
    addi    x6, zero, 8
    blt     x5, x6, _start       # while x5 < 8
    addi    x10, zero, 99
    ebreak
    .size   _start, .-_start
