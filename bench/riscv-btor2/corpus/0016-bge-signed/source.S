    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, -1         # x5 = 0xFFFFFFFFFFFFFFFF
                                 #   = -1 signed, 2^64 - 1 unsigned
    addi    x6, zero, 1
    bge     x5, x6, taken        # BGE is *signed* >=
                                 #   -1 >= 1 ? false, branch NOT taken
                                 # naive unsigned read: 2^64-1 >= 1 -> taken
    addi    x10, zero, 42        # fallthrough (signed says fall through)
    ebreak
taken:
    addi    x10, zero, 99
    ebreak
    .size   _start, .-_start
