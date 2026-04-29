    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x10, zero, 0
    jal     x1, callee
    ebreak
    .size   _start, .-_start

    .globl  callee
    .type   callee, @function
callee:
    addi    x5, zero, 5          # loop counter = 5
loop:
    addi    x10, x10, 1          # x10 += 1
    addi    x5, x5, -1           # counter -= 1
    bne     x5, zero, loop       # while counter != 0
    jr      x1
    .size   callee, .-callee
