    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x5, 0x80000          # x5 = 0xFFFFFFFF80000000 (high bit set)
    srai    x10, x5, 4           # SRAI: arithmetic shift; sign bit propagates
                                 #   x10 = 0xFFFFFFFFF8000000
                                 # NOT the logical-shift answer 0x0FFFFFFFF8000000
    ebreak
    .size   _start, .-_start
