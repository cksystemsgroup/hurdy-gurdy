    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 0          # counter
    addi    x6, zero, 16         # limit (twice as long as 0002)
loop:
    addi    x5, x5, 1
    bne     x5, x6, loop
    addi    x10, zero, 99        # post-loop marker
    ebreak
    .size   _start, .-_start
