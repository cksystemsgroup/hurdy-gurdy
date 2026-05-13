    .text
    .globl  _start
    .type   _start, @function
_start:
loop:
    mul     x5, x5, x6           # acc *= i  (the nonlinear step)
    addi    x6, x6, 1            # i++
    blt     x6, x7, loop         # while i < 7
    ebreak
    .size   _start, .-_start
