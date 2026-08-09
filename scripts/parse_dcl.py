"""Parse Thai DRG Appendix F1 DCL Table PDFs -> {icd10: {dc: dcl}}"""
import fitz, re, sys, os

CODE_RE = re.compile(r'^[A-Z]\d{2,5}$')
PAIR_RE = re.compile(r'^(\d{4}):(\d)$')
EQ_RE = re.compile(r'^=\s*([A-Z]\d{2,5})$')


def page_tokens(page):
    """Return tokens in column-major reading order (10 columns per page).

    Column anchors are the x-positions where DC:DCL pairs repeat many times;
    header/footer text is dropped first so it cannot bridge two columns.
    """
    h = page.rect.height
    words = [w for w in page.get_text("words")
             if 0.05 * h < w[1] < 0.97 * h]
    if not words:
        return []
    # anchors = x positions used by many tokens (the pair columns)
    freq = {}
    for w in words:
        freq[round(w[0], 1)] = freq.get(round(w[0], 1), 0) + 1
    peaks = sorted(x for x, n in freq.items() if n >= 10)
    anchors = []
    for x in peaks:
        if not anchors or x - anchors[-1] > 25:
            anchors.append(x)
    if not anchors:
        anchors = [min(w[0] for w in words)]

    def colidx(x):
        return min(range(len(anchors)), key=lambda i: abs(x - anchors[i]))

    items = [(colidx(w[0]), round(w[1], 1), w[4]) for w in words]
    items.sort(key=lambda t: (t[0], t[1]))
    # merge tokens on same (col,y) line
    out, cur, key = [], [], None
    for c, y, t in items:
        k = (c, y)
        if k != key:
            if cur:
                out.append(' '.join(cur))
            cur, key = [], k
        cur.append(t)
    if cur:
        out.append(' '.join(cur))
    return out


def parse_pdf(path, verbose=False):
    doc = fitz.open(path)
    data = {}          # code -> {dc: dcl}
    alias = {}         # code -> ref code
    cur = None
    started = False
    for pno in range(doc.page_count):
        toks = page_tokens(doc[pno])
        for tok in toks:
            t = tok.strip()
            if not t:
                continue
            m = PAIR_RE.match(t)
            if m:
                if cur:
                    data[cur][m.group(1)] = int(m.group(2))
                    started = True
                continue
            m = EQ_RE.match(t.replace('= ', '=').replace('=', '= ', 1))
            if m:
                if cur:
                    alias[cur] = m.group(1)
                continue
            if CODE_RE.match(t):
                cur = t
                data.setdefault(cur, {})
                continue
            # header/footer noise ignored
    # resolve aliases
    for c, ref in alias.items():
        seen = set()
        r = ref
        while r in alias and r not in seen:
            seen.add(r)
            r = alias[r]
        data[c] = dict(data.get(r, {}))
    return {k: v for k, v in data.items() if v}, alias


if __name__ == '__main__':
    p = sys.argv[1]
    data, alias = parse_pdf(p)
    print('codes with DCL:', len(data), 'aliases:', len(alias))
    for c in ['J411', 'J418', 'J430', 'J431', 'J440', 'J441', 'J448', 'J449']:
        print(c, '0455 ->', data.get(c, {}).get('0455'), ' (#DC=%d)' % len(data.get(c, {})))
