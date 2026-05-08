    .text
    .globl  _start
    .type   _start, @function
_start:
    li      x5, 1                # x5 = 1
    sllw    x10, x5, x6          # x10 = sign_extend((1 << (x6 & 31))[31:0], 64)
    ebreak
    .size   _start, .-_start
