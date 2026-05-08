    .text
    .globl  _start
    .type   _start, @function
_start:
    li      x10, 99             # x10 = 99 (the value before cleanup)
    li      x6, 1               # condition register (1 means "fall through")
    beqz    x6, skip_cleanup    # not taken (x6 != 0)
cleanup:
    li      x10, 0              # cleanup zeroes x10  *** required PC ***
skip_cleanup:
    ebreak
    .size   _start, .-_start
