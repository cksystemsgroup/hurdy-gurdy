    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x5, 0x80000      # x5 = sign_extend(0x80000<<12, 64) = 0xFFFFFFFF80000000
    addiw   x10, x5, 0       # ADDIW: 32-bit add then sign-extend low 32 to 64
                             #   low32(x5 + 0) = 0x80000000
                             #   sign_extend(0x80000000, 64) = 0xFFFFFFFF80000000
    ebreak
    .size   _start, .-_start
