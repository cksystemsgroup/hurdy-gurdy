    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x0, x0, 99           # writes to x0 are silently dropped (SCHEMA §3)
    addi    x0, x0, -1           # so are these
    add     x0, x5, x6           # this too
    ebreak
    .size   _start, .-_start
