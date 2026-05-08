    .text
    .globl  _start
    .type   _start, @function
_start:
    li      x5, 1               # x5 = 1 (the value to shift)
    li      x6, 30              # initial shift amount
    li      x7, 4               # remaining iterations
loop:
    sllw    x10, x5, x6         # 32-bit shift left logical, shamt masked to 5 bits
    addi    x6, x6, 1           # x6 walks 30 -> 31 -> 32 -> 33
    addi    x7, x7, -1
    bnez    x7, loop
    ebreak
    .size   _start, .-_start
