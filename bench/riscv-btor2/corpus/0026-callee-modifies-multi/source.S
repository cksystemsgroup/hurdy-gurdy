    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x10, zero, 0
    addi    x11, zero, 0
    addi    x12, zero, 0
    jal     x1, callee
    add     x13, x10, x11        # x13 = result_x10 + result_x11
    add     x13, x13, x12        # x13 += result_x12
    ebreak
    .size   _start, .-_start

    .globl  callee
    .type   callee, @function
callee:
    addi    x10, zero, 1
    addi    x11, zero, 2
    addi    x12, zero, 3
    jr      x1
    .size   callee, .-callee
