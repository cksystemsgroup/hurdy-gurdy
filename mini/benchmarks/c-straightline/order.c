#include <assert.h>
int nondet_int(void);

int main(void) {
  int a = nondet_int();
  int b = nondet_int();
  if (a >= 0 && b >= 0 && a < 10000 && b < 10000) {
    int lo = a < b ? a : b;
    int hi = a < b ? b : a;
    assert(lo <= hi);
  }
  return 0;
}
