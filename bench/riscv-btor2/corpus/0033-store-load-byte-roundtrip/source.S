    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x40            # x6 = 0x40000 (writable scratch address)
    li      x5, 0xCAFEBABE      # 64-bit constant (zero-extended in 64)
    sd      x5, 0(x6)           # mem[0x40000..0x40007] = 0xCAFEBABE (LE)
    ld      x10, 0(x6)          # x10 = mem[0x40000..0x40007] as bv64
    ebreak
    .size   _start, .-_start
