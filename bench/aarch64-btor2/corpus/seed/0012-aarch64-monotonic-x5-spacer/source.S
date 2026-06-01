    .text
    .globl  _start
    .type   _start, %function
_start:
    add     x5, x5, #1      /* x5 += 1 (x5 starts at 0 via RegisterInit) */
    mov     x6, #8
    cmp     x5, x6
    b.lt    _start           /* while x5 < 8 */
    mov     x0, #0
    svc     #0               /* normal halt; x5 stays in [1..8] */
    .size   _start, .-_start
