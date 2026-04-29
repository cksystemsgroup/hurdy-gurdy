    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x40             # x6 = 0x40000 (storage address)
    lui     x5, 0x1              # x5 = 0x1000
    addi    x5, x5, 0x234        # x5 = 0x1234
    sh      x5, 0(x6)            # store low 16 bits little-endian:
                                 #   mem[0x40000] = 0x34   (low byte)
                                 #   mem[0x40001] = 0x12   (high byte)
    lbu     x10, 0(x6)           # load 1 byte at 0x40000 -> 0x34
    ebreak
    .size   _start, .-_start
