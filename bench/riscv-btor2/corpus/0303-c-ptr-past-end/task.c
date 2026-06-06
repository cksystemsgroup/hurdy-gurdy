// 0303-c-ptr-past-end: lowering-sensitive — pointer arithmetic past one-past-the-end.
//
// C UB: C11 §6.5.6p8 states that the result of pointer addition is defined
// only when the resulting pointer points within the array or one past the end.
// A pointer pointing more than one element past the last element of an array
// object has undefined behaviour when formed; e.g. `arr + 5` where arr has
// 4 elements is UB because `arr + 4` (one-past-the-end) is the limit.
//
// On RV64 bare-metal, pointer arithmetic compiles to integer addition:
//   addi a5, s0, -48     # compute &arr[0] (stack address)
//   addi a5, a5, 20      # add 5*4 = 20 bytes → p (integer add, no OOB check)
// The hardware has no concept of pointer object bounds; any 64-bit address is
// a valid integer. The `p - arr` operation compiles to:
//   sub  a5, a4, a5      # byte difference
//   srai a5, a5, 0x2     # divide by sizeof(int)=4
// giving 20/4 = 5. On RV64, this is deterministically 5 regardless of whether
// a C-level checker considers the pointer formation UB.
//
// The trap fires only if diff != 5. Since the RV64 ISA computes diff = 5
// deterministically, the trap is provably unreachable.
//
// A C-level verifier with pointer-check enabled will flag the pointer
// arithmetic as past the end of the array object and report VERIFICATION
// FAILED (false positive), because from its model forming `arr + 5` is UB.
//
// CBMC (--pointer-check): flags `pointer relation: pointer outside object
// bounds in p` → VERIFICATION FAILED (false positive).
// ESBMC (default): no pointer-bounds check on arithmetic → VERIFICATION
// SUCCESSFUL (correct).
// Hurdy-gurdy: models the RV64 ELF; pointer arithmetic = ADDI instruction;
// diff = 5 deterministically → trap unreachable → PASS (correct).

extern void trap(void) __attribute__((noreturn));

void _start(void) {
    int arr[4];
    arr[0] = 0; arr[1] = 1; arr[2] = 2; arr[3] = 3;
    /* UB: pointer arithmetic past one-past-the-end (arr+4 is valid; arr+5 is UB) */
    int *p = arr + 5;
    /* On RV64, pointer arithmetic = integer addition; no trap, no special sentinel. */
    /* p points 5*4=20 bytes past arr[0]. */
    long diff = (long)(p - arr);  /* RV64: byte_diff / sizeof(int) = 20/4 = 5 */
    if (diff != 5L) trap();       /* assertion holds on RV64 — trap is unreachable */
    __asm__ volatile ("ebreak");  /* normal halt */
}

void trap(void) {
    __asm__ volatile ("ebreak");  /* bad halt — distinct PC */
    __builtin_unreachable();
}
