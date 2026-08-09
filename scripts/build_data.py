"""Assemble the web-app dataset from: DCL PDFs (6.3.3) + TDS6307 DBFs + grouper sweep."""
import csv, json, os, sys, collections
import dbf as D
from age_split_table import AGE_SPLIT

OUTDIR = 'data'


def load():
    _, i10 = D.read_dbf('data/c63i10.dbf')
    _, drg = D.read_dbf('data/c63drg.dbf')
    _, vx = D.read_dbf('data/C63i10vx.dbf')
    dcl = json.load(open('dcl633.json'))
    rows = list(csv.DictReader(open('results.csv', newline='', encoding='utf-8')))
    if os.path.exists('results_pass2.csv'):
        rows += list(csv.DictReader(open('results_pass2.csv', newline='', encoding='utf-8')))
    return i10, drg, vx, dcl, rows


def derive_pdc2dc(rows):
    """PDC -> DC, by majority vote over the codes actually fired at the grouper."""
    votes = collections.defaultdict(collections.Counter)
    for r in rows:
        if r['status'].startswith('ok') and r['drg'] and r['drg'] != '26509':
            votes[r['pdc']][r['drg'][:4]] += 1
    out, conflicts = {}, {}
    for pdc, c in votes.items():
        dc, n = c.most_common(1)[0]
        out[pdc] = dc
        if len(c) > 1:
            conflicts[pdc] = dict(c)
    return out, conflicts


def main():
    i10, drg, vx, dcl, rows = load()
    os.makedirs(OUTDIR, exist_ok=True)

    pdc2dc, conflicts = derive_pdc2dc(rows)
    print('PDC mapped: %d   conflicting PDC: %d' % (len(pdc2dc), len(conflicts)))
    for p, c in list(conflicts.items())[:10]:
        print('   conflict PDC %s -> %s' % (p, c))

    desc = {r['CODE']: r['DESC'].strip() for r in vx}

    # DRG levels per DC
    dcinfo = {}
    for r in drg:
        d = dcinfo.setdefault(r['DC'], {'mdc': r['MDC'], 'name': '', 'levels': {}})
        lvl = r['DRG'][4]
        d['levels'][lvl] = {'drg': r['DRG'], 'rw': r['RW'], 'wtlos': r['WTLOS'], 'ot': r['OT']}
        nm = r['DRGNAME']
        for suf in (' wo sig CCC', ' w min CCC', ' w mod CCC', ' w maj CCC', ' w ext CCC'):
            if nm.endswith(suf):
                nm = nm[:-len(suf)]
                break
        if not d['name'] or len(nm) < len(d['name']):
            d['name'] = nm

    # direct grouper answers (code -> DRG) for the codes actually fired
    fired = {r['code']: r['drg'] for r in rows if r['status'].startswith('ok') and r['drg']}

    # main table: one row per PDx-eligible ICD-10
    main = []
    for r in i10:
        if r['ACCPDX'] != 'Y':
            continue
        code, pdc = r['CODE'], r['PDC']
        if r['MDC'] == '15':
            # Newborn DCs are chosen by admission weight, not by the diagnosis:
            # the same code lands in 1552/1553/1554 at 1/2/3 kg. There is no
            # single DRG group for these codes.
            main.append({'c': code, 'd': desc.get(code, ''), 'mdc': r['MDC'],
                         'pdc': pdc, 'dc': '', 'dcl': 0, 'sex': r['SEX'],
                         'src': 'newborn-weight'})
            continue
        dc = (fired.get(code) or '')[:4] or pdc2dc.get(pdc, '')
        src = 'grouper' if code in fired else ('pdc' if dc else 'none')
        row = {
            'c': code, 'd': desc.get(code, ''), 'mdc': r['MDC'], 'pdc': pdc,
            'dc': dc, 'dcl': dcl.get(code, {}).get(dc, 0) if dc else 0,
            'sex': r['SEX'], 'src': src,
        }
        if pdc in AGE_SPLIT:
            cutoff, dc_young, dc_old = AGE_SPLIT[pdc]
            row['dc'] = dc_old
            row['dcl'] = dcl.get(code, {}).get(dc_old, 0)
            row['ageSplit'] = {
                'cutoff': cutoff,
                'young': {'dc': dc_young, 'dcl': dcl.get(code, {}).get(dc_young, 0)},
                'old': {'dc': dc_old, 'dcl': dcl.get(code, {}).get(dc_old, 0)},
            }
        main.append(row)
    json.dump(main, open(OUTDIR + '/main.json', 'w'), separators=(',', ':'))
    print('main rows', len(main), 'with DC', sum(1 for m in main if m['dc']),
          'from grouper', sum(1 for m in main if m['src'] == 'grouper'))

    meta = {'dclCodes': len(dcl), 'grouperVerified': sum(1 for m in main if m['src'] == 'grouper'),
            'newborn': sum(1 for m in main if m['src'] == 'newborn-weight'),
            'firedCodes': len(fired)}
    json.dump({'dc': dcinfo, 'pdc2dc': pdc2dc, 'conflicts': conflicts, 'meta': meta},
              open(OUTDIR + '/drg.json', 'w'), separators=(',', ':'))

    # Full DCL table. Storing "0011:1,0012:2,..." per code costs 19 MB; storing one
    # digit per DC against a shared DC index costs ~3.5 MB and looks up in O(1).
    dclist = sorted({dc for m in dcl.values() for dc in m})
    pos = {dc: i for i, dc in enumerate(dclist)}
    codes = {}
    for code, m in dcl.items():
        buf = ['0'] * len(dclist)
        for dc, v in m.items():
            buf[pos[dc]] = str(v)
        codes[code] = ''.join(buf)
    json.dump({'dcs': dclist, 'codes': codes},
              open(OUTDIR + '/dcl.json', 'w'), separators=(',', ':'))
    print('dcl: %d DCs x %d codes' % (len(dclist), len(codes)))

    # descriptions are only needed for codes the app can actually show
    wanted = {r['CODE'] for r in i10} | set(dcl)
    json.dump({k: v for k, v in desc.items() if k in wanted},
              open(OUTDIR + '/desc.json', 'w'), separators=(',', ':'))
    print('sizes:', {f: os.path.getsize(OUTDIR + '/' + f) // 1024
                     for f in sorted(os.listdir(OUTDIR))})


if __name__ == '__main__':
    main()
