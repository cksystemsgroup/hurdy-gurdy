    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x6, 0x40000          # x6 = 0x40000000 (outside any PT_LOAD;
                                 #   .text starts at 0x10000)
    ld      x10, 0(x6)           # 8-byte load from uninitialized memory
                                 # SCHEMA.md §4: bytes outside PT_LOAD are FREE,
                                 # not silently zeroed
    ebreak
    .size   _start, .-_start
