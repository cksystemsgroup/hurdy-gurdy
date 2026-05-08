    .text
    .globl  _start
    .type   _start, @function
_start:
    lui     x2, 0x40            # x2 = 0x40000 (sp; pretend stack base)
    li      x5, 0xCAFEBABE      # canary value
    sd      x5, 0(x2)           # spill x5 to stack
    li      x5, 0               # clobber x5 (simulate a function body)
    ld      x10, 0(x2)          # reload from stack into x10
    ebreak
    .size   _start, .-_start
