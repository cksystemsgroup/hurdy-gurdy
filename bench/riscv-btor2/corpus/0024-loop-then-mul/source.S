    .text
    .globl  _start
    .type   _start, @function
_start:
loop:
    addi    x5, x5, 1            # x5 += 1 (starts at 0 via RegisterInit)
    addi    x6, zero, 5
    bne     x5, x6, loop         # while x5 != 5
    mul     x10, x5, x5          # x10 = 5 * 5 = 25
    ebreak
    .size   _start, .-_start
