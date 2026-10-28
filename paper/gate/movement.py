"""The data of fig:movement: the board after every play and regrade
event of each pinned run, computed from the log alone. Run from the
repository root at tag era6-campaign-3:

    python3 paper/gate/movement.py

For each run the log is read in file order; each `play` or `regrade`
event starts a step, and the board at the end of a step is
best-per-question (kernel.results.best) over the log prefix so far,
counted as certified universal answers (grade certified, not a
witness), replayed witnesses, checked universal answers (grade
checked), bare claims (grade claimed), and open questions."""
import sys
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from kernel import results as R

RUNS = ['hwmcc24-mini', 'svcomp25-mini', 'hwmcc24-mid', 'hwmcc24-arrays']


def board(bench, qs, prefix):
    b = R.best(bench, prefix)
    cnt = {'certified': 0, 'witness': 0, 'checked': 0, 'claimed': 0, 'open': 0}
    for qid, q in qs.items():
        r = b.get(qid)
        if r is None or not R.settled(q, r['value']):
            cnt['open'] += 1
        elif r['value'].get('kind') == 'witness':
            cnt['witness'] += 1
        else:
            cnt[r.get('grade', 'claimed')] += 1
    return cnt


def main():
    for run in RUNS:
        bench = R.load_benchmark(f'runs/{run}/benchmark.json')
        recs = R.load(f'runs/{run}/log.jsonl')
        qs = bench['questions'] if isinstance(bench.get('questions'), dict) \
            else {q['id']: q for q in bench['questions']}
        print(f'== {run}: {len(qs)} asked')
        prefix, step = [], None
        for r in recs:
            if r.get('event') in ('play', 'regrade'):
                if step is not None:
                    print('  ', step, board(bench, qs, prefix))
                step = (r['event'], r.get('iteration'), r.get('via'),
                        (r.get('caps') or {}).get('wall_s'))
            else:
                prefix.append(r)
        print('  ', step, board(bench, qs, prefix))


if __name__ == '__main__':
    sys.exit(main())
