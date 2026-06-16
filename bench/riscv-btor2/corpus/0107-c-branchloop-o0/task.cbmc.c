// 010X-c-branchloop-oN family: same C source, four gcc -O levels.
//
// Loop with a parity-conditional inside: even iterations contribute
// 2*i, odd iterations contribute i. Tests how each -O level handles
// the inner branch — at -O0 it's an explicit if-else; at -O1+ gcc
// may rewrite it as a select, hoist the branch, or unroll partially.
// The expected sum is invariant; only the BTOR2 trace shape varies.

extern void trap(void) ;

int main(void) {
    volatile int n = 8;          // volatile blocks compile-time folding
    int sum = 0;
    for (int i = 0; i < n; i++) {
        if (i & 1) {
            sum += i;            // odd:  1 + 3 + 5 + 7  = 16
        } else {
            sum += 2 * i;        // even: 0 + 4 + 8 + 12 = 24
        }
    }
    if (sum != 40) trap();       // 16 + 24 = 40
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
