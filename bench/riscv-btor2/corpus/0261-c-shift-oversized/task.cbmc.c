// 0261-c-shift-oversized: lowering-sensitive — left-shift by >= int width at -O0.
//
// In C, `x << s` where s is a runtime value of 32 is undefined behaviour
// (shift amount >= type width). gcc at -O0 on RV64 emits `sllw rd, rs1, rs2`,
// which masks the shift amount to the low 5 bits (RISC-V ISA §4.2):
//   32 & 0x1f = 0
// The result is rs1 << 0 = rs1, sign-extended to 64 bits.
//
// A C-level analyser may claim "UB, any result is possible" and report
// `trap` reachable; hurdy-gurdy models `sllw`'s 5-bit masking and proves
// `trap` unreachable.

extern void trap(void) ;

int main(void) {
    volatile int x = 1;
    volatile int s = 32;         // shift by 32: C UB (>= int width)
    int y = x << s;               // RV64 sllw: 32 & 0x1f = 0, y = x = 1
    if (y != 1) trap();           // assertion holds — trap unreachable
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
