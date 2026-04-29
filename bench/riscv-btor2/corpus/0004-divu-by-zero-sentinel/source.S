    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 7      # dividend
    addi    x6, zero, 0      # divisor = 0
    divu    x10, x5, x6      # RV64M: divu by zero -> quotient = 2^64 - 1
                             # NOT a trap; NOT undefined behaviour
    ebreak
    .size   _start, .-_start
