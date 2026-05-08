    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, x5, 1            # x5 += 1 (x5 starts at 0 via RegisterInit)
    addi    x6, x0, 10
    blt     x5, x6, _start       # while x5 < 10; loop exits with x5 = 10
    ebreak                       # no further writes; x5 stays at 10
    .size   _start, .-_start
