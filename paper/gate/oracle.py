"""The oracle column (KERNEL.md §6, relative performance), drawn beside
the paper from recorded testimony: for every question of the pinned
runs, the board's best result (value, grade, seconds spent) beside the
best official solver's time from the competition results pinned under
oracles/packs/domains/, and the pinned oracle's time on this host when
a calibration record exists. Run from the repository root:

    python3 paper/gate/oracle.py            # the table, markdown
    python3 paper/gate/oracle.py --summary  # per board, the ratios
    python3 paper/gate/oracle.py --slice    # the 900 s plays, row per (question, route)
    python3 paper/gate/oracle.py --slice-summary  # per board, how the 900 s routes ended, and the host oracle

Nothing here is a grade: cost is recorded and never ranked by the
kernel, and this script ranks nothing either — it prints two columns
side by side."""
import collections, csv, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from kernel import results as R  # noqa: E402
RUNS = ['hwmcc24-mini', 'svcomp25-mini', 'hwmcc24-mid', 'hwmcc24-arrays']
PACKS = os.path.join(ROOT, 'oracles', 'packs', 'domains')


def hwmcc():
    """benchmark path -> list of (solver, result, real seconds) rows."""
    out = {}
    for f in ('hwmcc24-results-bv.csv', 'hwmcc24-results-array.csv'):
        for r in csv.DictReader(open(os.path.join(PACKS, 'hardware', f))):
            out.setdefault(r['benchmark'], []).append((r['solver'], r['result'], float(r['time_real'])))
    return out


def svcomp():
    """task yml -> list of (verifier, outcome, cpu seconds, verdict) rows."""
    out = {}
    for r in csv.DictReader(open(os.path.join(PACKS, 'software', 'svcomp25-results-reachsafety.csv'))):
        out.setdefault(r['benchmark'], []).append((r['solver'], r['outcome'], float(r['cputime_s']), r['status']))
    return out


def calibration(domain):
    path = os.path.join(PACKS, domain, 'calibration.jsonl')
    out = {}
    if os.path.exists(path):
        for line in open(path):
            rec = json.loads(line)
            if 'question' in rec:
                out[(rec['run'], rec['question'])] = rec
    return out


def official_best(q, hw, sv):
    """(solver, seconds) of the fastest official solver that answered
    the question's verdict, or None."""
    src = q['source']
    if src.startswith('hwmcc24 btor2/'):
        rows = hw.get(src[len('hwmcc24 btor2/'):], [])
        want = 'sat' if q['mode'] == 'exists' else 'unsat'
        ok = [(t, s) for s, res, t in rows if res == want]
    else:
        yml = src[src.index('(') + 1:src.index(')')]
        rows = sv.get(yml, [])
        # correct-unconfirmed: the verdict was right, the witness not
        # validated by the competition; the pinned `official` strings count it
        ok = [(t, s) for s, outc, t, st in rows if outc in ('correct', 'correct-unconfirmed')]
    return (min(ok)[1], min(ok)[0]) if ok else None


def _outcome(rec):
    v = rec['value']
    if v.get('kind') == 'witness':
        return f"witness depth {v['depth']}, {rec['grade']}"
    if v.get('kind') == 'all':
        return f"all({v['bound']}), {rec['grade']}"
    return 'partial: ' + v.get('progress', {}).get('note', '')


def slice_table(hw, sv):
    """Every record of the plays with a 900 s wall, beside the official
    best and the host calibration; the board's grade of the question
    before that play and after it."""
    for run in RUNS:
        bench = R.load_benchmark(os.path.join(ROOT, 'runs', run, 'benchmark.json'))
        recs = R.load(os.path.join(ROOT, 'runs', run, 'log.jsonl'))
        qs = bench['questions'] if isinstance(bench.get('questions'), dict) \
            else {q['id']: q for q in bench['questions']}
        cal = calibration('hardware' if run.startswith('hwmcc') else 'software')
        plays = [i for i, r in enumerate(recs) if r.get('event') == 'play' and r['caps'].get('wall_s') == 900.0]
        if not plays:
            continue
        i0 = plays[0]
        before = R.best(bench, [r for r in recs[:i0] if r.get('event') not in ('play', 'regrade')])
        after = R.best(bench, [r for r in recs if r.get('event') not in ('play', 'regrade')])
        its = {recs[i]['iteration'] for i in plays}
        rows = [r for r in recs if r.get('event') is None and r.get('iteration') in its]
        print(f"\n## {run}: {len(rows)} routes played at 900 s\n")
        print("| question | route | official best (s) | host oracle (s) | outcome at 900 s | spent (s) | board before → after |\n|---|---|---|---|---|---|---|")
        def grade(b, qid, q):
            r = b.get(qid)
            if not r or not R.settled(q, r['value']):
                return 'open'
            return 'witness' if r['value'].get('kind') == 'witness' else r['grade']
        for r in rows:
            qid, q = r['question'], qs[r['question']]
            off = official_best(q, hw, sv)
            c = cal.get((run, qid))
            print(f"| {qid} | {' '.join(r['route'])} | {off[0] + ' ' + f'{off[1]:.1f}' if off else '—'} | "
                  f"{(c['result'] + ' ' + f'{c['wall_s']:.1f}') if c else ''} | {_outcome(r)} | "
                  f"{r['budget']['spent_s']:.1f} | {grade(before, qid, q)} → {grade(after, qid, q)} |")


def _class(rec, q):
    v = rec['value']
    if v.get('kind') == 'witness':
        return 'witness'
    if v.get('kind') == 'all':
        if R.covers(v['bound'], q['bound']):
            return 'covering claim'
        if q['bound'] == 'inf' and v['bound'] == 300:
            return 'depth ceiling (300 frames)'
        return 'bare claim below the ask'
    note = v.get('progress', {}).get('note', '')
    if 'rc=-9' in note or 'nondeterministic' in note:
        return 'killed by the host memory guard'
    if 'rc=1' in note:
        return 'search out of memory'
    if 'twice' in note:
        return 'killed at twice the wall'
    return 'partial: ' + note


def slice_summary(hw, sv):
    for run in RUNS:
        bench = R.load_benchmark(os.path.join(ROOT, 'runs', run, 'benchmark.json'))
        recs = R.load(os.path.join(ROOT, 'runs', run, 'log.jsonl'))
        qs = bench['questions'] if isinstance(bench.get('questions'), dict) \
            else {q['id']: q for q in bench['questions']}
        plays = [i for i, r in enumerate(recs) if r.get('event') == 'play' and r['caps'].get('wall_s') == 900.0]
        if not plays:
            continue
        i0 = plays[0]
        before = R.best(bench, [r for r in recs[:i0] if r.get('event') not in ('play', 'regrade')])
        after = R.best(bench, [r for r in recs if r.get('event') not in ('play', 'regrade')])
        its = {recs[i]['iteration'] for i in plays}
        rows = [r for r in recs if r.get('event') is None and r.get('iteration') in its]
        qids = sorted({r['question'] for r in rows})
        def settled(b, qid):
            r = b.get(qid)
            return bool(r and R.settled(qs[qid], r['value']))
        moved = [q for q in qids if settled(after, q) and not settled(before, q)]
        cls = collections.Counter(_class(r, qs[r['question']]) for r in rows)
        spent = [r['budget']['spent_s'] for r in rows]
        print(f"== {run}: {len(qids)} questions, {len(rows)} routes at 900 s; newly settled {len(moved)} {moved}")
        for k, n in cls.most_common():
            print(f"   {n:3d} {k}")
        print(f"   spent per route: median {statistics.median(spent):.0f}s, max {max(spent):.0f}s")
        cal = calibration('hardware' if run.startswith('hwmcc') else 'software')
        mine = [c for (rn, q), c in cal.items() if rn == run]
        if mine:
            cc = collections.Counter(c['result'] for c in mine)
            sl = [cal[(run, q)] for q in qids if (run, q) in cal]
            print(f"   host oracle on all {len(mine)} existential questions: {dict(cc)}; on the {len(sl)} slice questions: {dict(collections.Counter(c['result'] for c in sl))}")
            for q in qids:
                c = cal.get((run, q)); off = official_best(qs[q], hw, sv)
                a = after.get(q)
                print(f"      {q}: official {off[0] + ' ' + f'{off[1]:.1f}' if off else '—'}; host {c['result'] + ' ' + f'{c['wall_s']:.0f}' if c else '—'}; "
                      f"board {_class(a, qs[q]) if a else 'open'} {a['budget']['spent_s']:.0f}s" if a else '')


def main(argv):
    hw, sv = hwmcc(), svcomp()
    summary = '--summary' in argv
    if '--slice-summary' in argv:
        slice_summary(hw, sv)
        return 0
    if '--slice' in argv:
        slice_table(hw, sv)
        return 0
    for run in RUNS:
        bench = R.load_benchmark(os.path.join(ROOT, 'runs', run, 'benchmark.json'))
        recs = R.load(os.path.join(ROOT, 'runs', run, 'log.jsonl'))
        qs = bench['questions'] if isinstance(bench.get('questions'), dict) \
            else {q['id']: q for q in bench['questions']}
        best = R.best(bench, [r for r in recs if r.get('event') not in ('play', 'regrade')])
        cal = calibration('hardware' if run.startswith('hwmcc') else 'software')
        rows, ratios, open_solved = [], [], []
        for qid, q in qs.items():
            r = best.get(qid)
            settled = bool(r and R.settled(q, r['value']))
            off = official_best(q, hw, sv)
            c = cal.get((run, qid))
            spent = r['budget']['spent_s'] if r else None
            kind = ('witness' if r['value'].get('kind') == 'witness' else r.get('grade')) if settled else 'open'
            rows.append((qid, q['mode'], str(q['bound']), kind, spent, off, c))
            if settled and off:
                ratios.append(spent / off[1] if off[1] > 0 else float('inf'))
            if not settled and off:
                open_solved.append(off[1])
        if summary:
            fin = [x for x in ratios if x != float('inf')]
            print(f"== {run}: {len(qs)} asked; settled with an official time {len(ratios)}; "
                  f"ratio spent/official median {statistics.median(fin):.1f}, "
                  f"min {min(fin):.2f}, max {max(fin):.0f}" if fin else f"== {run}")
            if open_solved:
                print(f"   open but officially solved {len(open_solved)}: official best median "
                      f"{statistics.median(open_solved):.1f}s, max {max(open_solved):.0f}s")
            continue
        print(f"\n## {run}\n\n| question | ask | best result | spent (s) | best official | official (s) | host oracle (s) |\n|---|---|---|---|---|---|---|")
        for qid, mode, bound, kind, spent, off, c in rows:
            ask = f"{'∃' if mode == 'exists' else '∀'} {bound}"
            print(f"| {qid} | {ask} | {kind} | {'' if spent is None else f'{spent:.1f}'} | "
                  f"{off[0] if off else '—'} | {f'{off[1]:.1f}' if off else '—'} | "
                  f"{'' if not c else (f'{c['wall_s']:.1f}' + (' ' + c['result'] if c.get('result') else ''))} |")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
