    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x40            # x6 = 0x40000
    li      x5, 0x12345678
    sw      x5, 0(x6)           # mem[0..3] = 78 56 34 12 (little-endian)
    li      x5, 0xFF
    sb      x5, 0(x6)           # mem[0] = FF; mem[1..3] unchanged
    lw      x10, 0(x6)          # load word, sign-extend to 64
                                #   bytes 78->FF 56 34 12 -> word 0x123456FF
                                #   bit 31 = 0, so zero-extend: x10 = 0x123456FF
    ebreak
    .size   _start, .-_start
