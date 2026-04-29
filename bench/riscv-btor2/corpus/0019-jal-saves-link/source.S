    .text
    .globl  _start
    .type   _start, @function
_start:
    jal     x10, target          # x10 = pc + 4 (= 0x10004); pc -> target
    addi    x11, zero, 99        # never reached
    ebreak                       # never reached
target:
    ebreak
    .size   _start, .-_start
