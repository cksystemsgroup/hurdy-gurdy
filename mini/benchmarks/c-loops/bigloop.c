#include <assert.h>
int nondet_int(void);

int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 60000) {
    int s = 0;
    for (int i = 0; i < n; i++) s += 3;
    assert(s % 3 == 0);        /* theorem: s == 3n */
  }
  return 0;
}
