    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x10, zero, 2         # x10 = 2
    addi    x11, zero, 3         # multiplier
    mul     x10, x10, x11        # x10 = 6
    mul     x10, x10, x11        # x10 = 18
    mul     x10, x10, x11        # x10 = 54
    mul     x10, x10, x11        # x10 = 162
    mul     x10, x10, x11        # x10 = 486
    mul     x10, x10, x11        # x10 = 1458
    mul     x10, x10, x11        # x10 = 4374
    mul     x10, x10, x11        # x10 = 13122
    mul     x10, x10, x11        # x10 = 39366
    ebreak                       # halt
    .size   _start, .-_start
