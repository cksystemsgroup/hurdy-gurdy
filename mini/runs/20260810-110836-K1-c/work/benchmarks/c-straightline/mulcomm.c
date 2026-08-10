#include <assert.h>
int nondet_int(void);

int main(void) {
  int x = nondet_int();
  int y = nondet_int();
  assert(x * y == y * x);      /* theorem; bit-blasting groans */
  return 0;
}
