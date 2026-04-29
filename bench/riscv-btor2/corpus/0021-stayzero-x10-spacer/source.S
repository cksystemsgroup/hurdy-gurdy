    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, x5, 1            # increment x5 (just to keep program alive)
    beq     x5, x5, _start       # x5 == x5 always; infinite loop, no halt
    .size   _start, .-_start
