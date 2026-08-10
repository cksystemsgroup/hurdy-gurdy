#include <assert.h>
int nondet_int(void);

int main(void) {
  int n = nondet_int();
  if (n >= 0 && n <= 8) {
    int s = 0;
    for (int i = 0; i < n; i++) s += i;
    assert(s != 21);           /* n == 7 violates: 0+..+6 = 21 */
  }
  return 0;
}
