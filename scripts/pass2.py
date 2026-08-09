"""Pass 2: contexts that the standard adult-male case cannot reach, plus the one
PDC that turned out not to be homogeneous."""
import csv, os, time, collections
import runner
from runner import Session, kill_app
import dbf as D

OUT = 'results_pass2.csv'


def targets():
    _, i10 = D.read_dbf('data/c63i10.dbf')
    acc = [r for r in i10 if r['ACCPDX'] == 'Y']
    rows = list(csv.DictReader(open('results.csv', newline='', encoding='utf-8')))
    mapped = {r['pdc'] for r in rows if r['drg'] and r['drg'] != '26509'}
    unmapped = {r['PDC'] for r in acc} - mapped

    groups = collections.defaultdict(list)
    for r in acc:
        groups[r['PDC']].append(r)

    jobs = []   # (context, code, pdc, mdc)
    for pdc in sorted(unmapped):
        rs = sorted(groups[pdc], key=lambda r: r['CODE'])
        idx = sorted({0, len(rs) // 2, len(rs) - 1})[:3]
        # MDC 15 is newborns; MDC 13/14 are female-only
        ctx = 'newborn' if rs[0]['MDC'] == '15' else 'female'
        for i in idx:
            jobs.append((ctx, rs[i]['CODE'], pdc, rs[i]['MDC']))
    # PDC 25A splits across DCs, so every one of its codes must be fired
    for r in sorted(groups['25A'], key=lambda r: r['CODE']):
        jobs.append(('female' if r['SEX'] == 'F' else 'adult', r['CODE'], '25A', r['MDC']))
    return jobs


CONTEXTS = {
    'adult':   dict(AGE='70', SEX='1', DISC='1', WT='70', LOSD='3'),
    'female':  dict(AGE='30', SEX='2', DISC='1', WT='60', LOSD='3'),
    'newborn': dict(AGE='0',  SEX='1', DISC='1', WT='3',  LOSD='3'),
}


def main():
    jobs = targets()
    by_ctx = collections.defaultdict(list)
    for ctx, code, pdc, mdc in jobs:
        by_ctx[ctx].append((code, pdc, mdc))
    print('pass2 jobs: %s (total %d)' % ({k: len(v) for k, v in by_ctx.items()}, len(jobs)))

    new = not os.path.exists(OUT) or os.path.getsize(OUT) == 0
    f = open(OUT, 'a', newline='', encoding='utf-8')
    w = csv.writer(f)
    if new:
        w.writerow(['code', 'pdc', 'mdc', 'echo_pdx', 'drg', 'drgname', 'status', 'context'])

    for ctx in ('female', 'newborn', 'adult'):
        items = by_ctx.get(ctx)
        if not items:
            continue
        kill_app()
        for k, v in CONTEXTS[ctx].items():
            setattr(Session, k, v)
        s = Session(verify=False)
        print('--- context %s: age=%s sex=%s wt=%s (%d codes)'
              % (ctx, Session.AGE, Session.SEX, Session.WT, len(items)), flush=True)
        t0 = time.time()
        for i, (code, pdc, mdc) in enumerate(items, 1):
            res = None
            for mode in ('dbl', 'ctrla'):
                e, d, n, _ = s.query(code, mode=mode)
                if e == code and d:
                    res = (e, d, n)
                    break
            if res:
                w.writerow([code, pdc, mdc, res[0], res[1], res[2], 'ok', ctx])
            else:
                w.writerow([code, pdc, mdc, '', '', '', 'FAILED', ctx])
            f.flush()
            if i % 15 == 0 or i == len(items):
                print('   %d/%d %.0fs last %s->%s'
                      % (i, len(items), time.time() - t0, code,
                         res[1] if res else 'FAIL'), flush=True)
    f.close()
    print('DONE')


if __name__ == '__main__':
    main()
