    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x10, zero, 0
    jal     x1, add5             # x10 += 5
    jal     x1, mul3             # x10 *= 3
    ebreak
    .size   _start, .-_start

    .globl  add5
    .type   add5, @function
add5:
    addi    x10, x10, 5
    jr      x1
    .size   add5, .-add5

    .globl  mul3
    .type   mul3, @function
mul3:
    addi    x5, zero, 3
    mul     x10, x10, x5
    jr      x1
    .size   mul3, .-mul3
