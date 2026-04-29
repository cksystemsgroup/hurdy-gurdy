    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 12         # counter = 12
loop:
    addi    x5, x5, -1           # counter -= 1
    bne     x5, x0, loop         # while counter != 0
    addi    x10, zero, 99
    ebreak
    .size   _start, .-_start
