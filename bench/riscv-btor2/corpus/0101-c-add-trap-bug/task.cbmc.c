// 0101-c-add-trap-bug: deliberate-bug counterpart to 0100.
//
// Same shape as 0100, but the assertion is *reversed*: the program
// traps when c == 12 (which is always true). The trap is therefore
// always reached. Validates the auto-spec-gen pipeline on a
// `reachable`-verdict task and exercises the witness fingerprint
// path on a C-derived task.

extern void trap(void) ;

int main(void) {
    int a = 5;
    int b = 7;
    int c = a + b;
    if (c == 12) trap();
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
