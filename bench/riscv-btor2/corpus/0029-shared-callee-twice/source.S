    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x10, zero, 0
    jal     x1, inc              # x10 += 1
    jal     x1, inc              # x10 += 1 (second call)
    ebreak
    .size   _start, .-_start

    .globl  inc
    .type   inc, @function
inc:
    addi    x10, x10, 1
    jr      x1
    .size   inc, .-inc
