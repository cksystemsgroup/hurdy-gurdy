    .text
    .globl  _start
    .type   _start, @function
_start:
    jal     x1, callee             # call callee; x18 starts at 99 (RegisterInit)
    add     x10, x18, x0           # x10 = x18 (= 99 if callee preserved x18)
    ebreak                          # halt
    .size   _start, .-_start

    .globl  callee
    .type   callee, @function
callee:
    addi    x5, x0, 7              # callee uses x5/x6 only; never writes x18
    add     x6, x5, x5
    jalr    x0, x1, 0              # ret
    .size   callee, .-callee
