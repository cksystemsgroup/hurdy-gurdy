    .text
    .globl  _start
    .type   _start, @function
_start:
loop:
    addi    x5, x5, 3            # x5 += 3 (starts at 0 via RegisterInit)
    addi    x6, zero, 21
    blt     x5, x6, loop         # while x5 < 21
    addi    x10, zero, 99
    ebreak
    .size   _start, .-_start
