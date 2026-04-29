    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 12         # 0b1100
    addi    x6, zero, 10         # 0b1010
    or      x10, x5, x6          # 0b1110 = 14
    ebreak
    .size   _start, .-_start
