    .text
    .globl  _start
    .type   _start, %function
_start:
    add     x5, x5, #1      /* x5 += 1 (x5 starts at 0 via RegisterInit) */
    mov     x6, #10
    cmp     x5, x6
    b.lt    _start           /* while x5 < 10; exits with x5 = 10 */
    svc     #0               /* normal halt */
    .size   _start, .-_start
