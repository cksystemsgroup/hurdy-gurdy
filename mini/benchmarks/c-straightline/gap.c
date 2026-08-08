#include <assert.h>
int nondet_int(void);

int main(void) {
  int x = nondet_int();
  if (x > 0 && x < 100) {
    int y = x * 2 + 1;
    assert(y != 41);           /* x == 20 violates */
  }
  return 0;
}
