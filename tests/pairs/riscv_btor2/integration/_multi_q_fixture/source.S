    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x18, x0, 0       # init counter
    addi    x10, x0, 0       # init result
loop:
    addi    x18, x18, 1
    add     x10, x10, x18
    addi    x5, x0, 10
    bne     x18, x5, loop    # repeat until x18 == 10
    ebreak
    .size   _start, .-_start
