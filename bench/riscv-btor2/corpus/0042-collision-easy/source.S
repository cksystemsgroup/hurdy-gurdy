    .text
    .globl  _start
    .type   _start, @function
_start:
    li      x5, 10
    blt     x6, x5, lo           # if x6 < 10: lo path
hi:
    addi    x10, x6, -5          # hi path: x10 = x6 - 5
    j       done
lo:
    addi    x10, x6, 5           # lo path: x10 = x6 + 5
done:
    ebreak
    .size   _start, .-_start
