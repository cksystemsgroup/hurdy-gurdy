// 0123-c-endianness-le: lowering-sensitive — RV64 is little-endian
// at -O0.
//
// Storing 0x1234 to a 16-bit value and reading the underlying
// bytes exposes the byte order. RV64 is little-endian, so the
// low byte (0x34) is at offset 0 and the high byte (0x12) is at
// offset 1. SCHEMA.md §13 cites little-endian multi-byte layout
// as a lowering surface (mirrors hand-written 0010-lh-endianness).
//
// **Implementation note (v0.4 memory-model finding).** A direct
// pointer-cast from `unsigned short *` to `unsigned char *` —
// the obvious C idiom — triggers a 4-8× wall-clock penalty on
// the bench's BTOR2 model because z3 has to encode the load
// address as a value loaded from a stack slot. A `union` keeps
// the storage stack-allocated and the byte access compiles to a
// direct stack-relative load (`lbu`-with-static-offset), avoiding
// the symbolic-pointer cost. See CORPUS_V0.4_PLAN.md for the
// full diagnostic.

extern void trap(void) ;

int main(void) {
    union {
        volatile unsigned short s;
        unsigned char b[2];
    } u;
    u.s = 0x1234;
    if (u.b[0] != 0x34) trap();   // little-endian: low byte at offset 0
    if (u.b[1] != 0x12) trap();   // high byte at offset 1
    
}

void trap(void) { __CPROVER_assert(0, "trap reachable"); }
