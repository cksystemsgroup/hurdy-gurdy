#include <assert.h>
int nondet_int(void);

int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 40) {
    int k = n;
    while (k > 0) k -= 2;
    assert(k == 0 || k == -1);
  }
  return 0;
}
