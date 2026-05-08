    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x50            # x6 = 0x50000 (data region pinned via MemoryInit)
    lbu     x10, 0(x6)          # x10 = zero_extend(mem[0x50000])
    ebreak
    .size   _start, .-_start
