    .text
    .globl  _start
    .type   _start, @function
_start:
loop:
    mul     x5, x5, x6           # x5 *= 100  (each step adds 2 factors of 2)
    addi    x7, x7, 1            # iter++
    bne     x7, x8, loop         # while iter != 40
    ebreak
    .size   _start, .-_start
