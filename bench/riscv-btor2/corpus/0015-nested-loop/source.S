    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 0          # outer counter
    addi    x6, zero, 3          # outer limit
outer:
    addi    x7, zero, 0          # inner counter
    addi    x8, zero, 8          # inner limit
inner:
    addi    x7, x7, 1
    bne     x7, x8, inner
    addi    x5, x5, 1
    bne     x5, x6, outer
    addi    x10, zero, 99        # post-loop marker
    ebreak
    .size   _start, .-_start
