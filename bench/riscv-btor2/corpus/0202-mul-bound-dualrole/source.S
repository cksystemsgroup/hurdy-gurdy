    .text
    .globl  _start
    .type   _start, @function
_start:
loop:
    mul     x5, x5, x6           # x5 *= 3  (the nonlinear step)
    addi    x7, x7, 1            # i++
    bne     x7, x8, loop         # while i != 5
    addi    x10, x5, 0           # x10 = x5  (post-loop snapshot)
    ebreak
    .size   _start, .-_start
