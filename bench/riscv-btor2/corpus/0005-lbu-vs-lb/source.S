    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x20             # x6 = 0x20000000 (>= entry, away from .text)
    addi    x5, zero, -1         # x5 = 0xFFFFFFFFFFFFFFFF
    sb      x5, 0(x6)            # write 0xFF byte at 0x20000000
    lbu     x10, 0(x6)           # LBU: zero-extend the loaded byte
                                 # x10 = 0x00000000000000FF, NOT 0xFF...FF
    ebreak
    .size   _start, .-_start
