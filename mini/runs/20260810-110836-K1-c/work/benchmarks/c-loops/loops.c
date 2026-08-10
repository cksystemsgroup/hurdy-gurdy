#include <assert.h>
int nondet_int(void);

int main(void) {
  int s = 0;
  for (int i = 0; i < 6; i++) s += 2;
  assert(s == 12);
  return 0;
}
