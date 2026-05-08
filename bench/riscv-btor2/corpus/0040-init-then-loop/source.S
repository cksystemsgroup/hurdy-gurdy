    .text
    .globl  _start
    .type   _start, @function
_start:
    j       init                # jump over the "bad" block below
bad:
    li      x10, 999            # never executed (proves that init's
    ebreak                      #   required-PC check is meaningful)
init:                           #   *** required PC #1 ***
    li      x5, 0
    li      x6, 3
loop:                           #   *** required PC #2 ***
    addi    x5, x5, 7
    addi    x6, x6, -1
    bnez    x6, loop
    addi    x10, x5, 0          # x10 = 21 at halt
    ebreak
    .size   _start, .-_start
