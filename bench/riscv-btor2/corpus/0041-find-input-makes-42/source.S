    .text
    .globl  _start
    .type   _start, @function
_start:
    add     x10, x10, x10        # x10 = 2 * input
    addi    x10, x10, 14         # x10 = 2*input + 14
    ebreak
    .size   _start, .-_start
