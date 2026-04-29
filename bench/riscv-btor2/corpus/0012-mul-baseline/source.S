    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 7
    addi    x6, zero, 6
    mul     x10, x5, x6          # x10 = 7 * 6 = 42 (low 64 bits)
    ebreak
    .size   _start, .-_start
