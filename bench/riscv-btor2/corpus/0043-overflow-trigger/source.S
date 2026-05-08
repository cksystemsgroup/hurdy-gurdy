    .text
    .globl  _start
    .type   _start, @function
_start:
    addw    x10, x6, x6          # x10 = sign_extend(low32(x6 + x6), 64)
    ebreak
    .size   _start, .-_start
