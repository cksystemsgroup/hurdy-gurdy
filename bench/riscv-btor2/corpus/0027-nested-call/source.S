    .text
    .globl  _start
    .type   _start, @function
_start:
    jal     x1, A                # x1 = ret_to_start
    addi    x20, x10, 100        # x20 = x10_after_A + 100
    ebreak
    .size   _start, .-_start

    .globl  A
    .type   A, @function
A:
    jal     x6, B                # x6 = ret_to_A; uses x6 (t1) so x1 is preserved
    addi    x10, x10, 5          # x10 += 5 after B returns
    jr      x1                   # return to _start
    .size   A, .-A

    .globl  B
    .type   B, @function
B:
    addi    x10, x10, 7
    jr      x6                   # return to A
    .size   B, .-B
