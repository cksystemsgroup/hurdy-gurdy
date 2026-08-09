#include <assert.h>
int nondet_int(void);

int main(void) {
  int x = nondet_int();
  int m = x & 7;
  assert(m != 5);              /* any x with low bits 101 violates */
  return 0;
}
