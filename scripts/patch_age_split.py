"""Apply AGE_SPLIT to the already-built data/main.json in place.

Standalone alternative to a full build_data.py rerun, which needs source DBFs
and dcl633.json that aren't checked into this repo. Idempotent: codes already
carrying 'ageSplit' are recomputed, not duplicated.
"""
import json
from age_split_table import AGE_SPLIT

main = json.load(open('data/main.json', encoding='utf-8'))
dcl_tab = json.load(open('data/dcl.json', encoding='utf-8'))
pos = {dc: i for i, dc in enumerate(dcl_tab['dcs'])}


def dcl_of(code, dc):
    s = dcl_tab['codes'].get(code)
    if not s or dc not in pos:
        return 0
    return int(s[pos[dc]])


touched = 0
for row in main:
    ov = AGE_SPLIT.get(row.get('pdc'))
    if not ov:
        continue
    cutoff, dc_young, dc_old = ov
    row['dc'] = dc_old
    row['dcl'] = dcl_of(row['c'], dc_old)
    row['ageSplit'] = {
        'cutoff': cutoff,
        'young': {'dc': dc_young, 'dcl': dcl_of(row['c'], dc_young)},
        'old': {'dc': dc_old, 'dcl': dcl_of(row['c'], dc_old)},
    }
    touched += 1

json.dump(main, open('data/main.json', 'w', encoding='utf-8'), separators=(',', ':'))
print('patched %d codes across %d PDC families' % (touched, len(AGE_SPLIT)))
