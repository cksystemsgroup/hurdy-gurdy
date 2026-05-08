    .text
    .globl  _start
    .type   _start, @function
_start:
    li      x6, 5               # x6 = 5
    li      x7, 3               # x7 = 3
    bge     x6, x7, true_arm    # taken (5 >= 3)
false_arm:
    li      x10, 100            # NOT executed
    j       done
true_arm:
    li      x10, 200            # executed  *** required PC ***
done:
    ebreak
    .size   _start, .-_start
