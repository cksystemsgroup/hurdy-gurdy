    .text
    .globl  _start
    .type   _start, @function
_start:
    li      x5, 0x100           # x5 = 256 (multiplicand, doubles in width each iter)
    li      x6, 0               # x6 = product accumulator
    li      x7, 3               # remaining iterations
loop:
    mulw    x6, x5, x5          # 32-bit signed multiply, truncate to 32, sign-extend
    slli    x5, x5, 4           # x5 *= 16  (256 -> 4096 -> 65536 -> 1048576)
    addi    x7, x7, -1
    bnez    x7, loop
    ebreak
    .size   _start, .-_start
