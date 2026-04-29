    .text
    .globl  _start
    .type   _start, @function
_start:
    addi    x5, x0, 7        # x10000: x5 = 7
    addi    x0, x0, 99       # x10004: write to x0 — DROPPED per RV spec
    add     x10, x0, x5      # x10008: x10 = x0 + x5 = 0 + 7 = 7  (NOT 99 + 7)
    ebreak                   # x1000C: halt
    .size   _start, .-_start
