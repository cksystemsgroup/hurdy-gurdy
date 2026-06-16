// 0100-c-add-trap-correct: the C analogue of 0007-simple-add-baseline.
//
// Compute c = a + b with a=5, b=7, and trap if c != 12. The assertion
// always holds (c is always 12), so the trap is unreachable. This is
// the v0.4 C-corpus prototype that validates the _compile_c.py
// auto-spec-gen pipeline end-to-end.

extern void trap(void) ;

int main(void) {
    int a = 5;
    int b = 7;
    int c = a + b;
    if (c != 12) trap();
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
