#include <assert.h>
int nondet_int(void);

int main(void) {
  int x = nondet_int();
  if (x > 0 && x < 1000) {
    int y = x + x;
    assert(y > x);             /* holds on the guarded range */
  }
  return 0;
}
