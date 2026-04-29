    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x10, zero, 0
    jal     x1, callee           # x1 = ret_addr; jump to callee
    addi    x11, x10, 1          # x11 = x10_after_call + 1
    ebreak
    .size   _start, .-_start

    .globl  callee
    .type   callee, @function
callee:
    addi    x10, zero, 42
    jr      x1                   # return: jalr x0, 0(x1)
    .size   callee, .-callee
