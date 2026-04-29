    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, x0, 0        # x10000: counter = 0
    addi    x6, x0, 8        # x10004: limit   = 8
loop:
    addi    x5, x5, 1        # x10008: ++counter
    bne     x5, x6, loop     # x1000C: while (counter != 8) goto loop
    addi    x10, x0, 42      # x10010: post-loop marker
    ebreak                   # x10014: halt
    .size   _start, .-_start
