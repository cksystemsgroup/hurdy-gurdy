    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 5
    addi    x6, zero, 7
    add     x10, x5, x6          # straightforward; no lowering subtlety
    ebreak
    .size   _start, .-_start
