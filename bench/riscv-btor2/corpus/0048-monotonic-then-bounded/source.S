    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x18, x18, 1            # x18 += 1 (x18 starts at 0 via RegisterInit)
    addi    x6, x0, 10
    blt     x18, x6, _start        # while x18 < 10; loop exits with x18 = 10
    add     x10, x18, x0           # x10 = x18 (post-loop, so x10 = 10 specifically)
    ebreak                         # halt
    .size   _start, .-_start
