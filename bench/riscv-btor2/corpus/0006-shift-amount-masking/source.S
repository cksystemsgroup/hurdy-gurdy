    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, zero, 64         # would-be shift amount (out of range)
    addi    x6, zero, 1
    sll     x10, x6, x5          # SLL on RV64: shift amount is x5[5:0]
                                 # 64 & 0x3F = 0 -> x10 = 1 << 0 = 1
                                 # NOT 1 << 64 = 0
    ebreak
    .size   _start, .-_start
