    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, -1         # x5 = 0xFFFFFFFFFFFFFFFF
                                 #   = -1 signed, 2^64 - 1 unsigned
    addi    x6, zero, 1
    bgeu    x5, x6, taken        # BGEU is *unsigned* >=
                                 #   2^64-1 >= 1 -> branch taken
                                 # naive signed read: -1 < 1 -> falls through
    addi    x10, zero, 99        # would-be fallthrough marker
    ebreak
taken:
    addi    x10, zero, 42
    ebreak
    .size   _start, .-_start
