"""Fold index.html + data/*.json into one self-contained page.

Used for the shareable demo build: the page keeps its fetch('data/x.json')
calls untouched and a shim resolves them out of inlined <script type=
"application/json"> blocks, so index.html stays the single source of truth.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
DATA = ['main', 'drg', 'desc', 'dcl']

SHIM = """
/* single-file build: serve data/*.json from the inlined blocks below */
window.fetch = function(u){
  const k = String(u).replace(/^.*\\//, '').replace(/\\.json$/, '');
  const el = document.getElementById('d-' + k);
  if(!el) return Promise.reject(new Error('no inlined data for ' + u));
  return Promise.resolve({ ok:true, json: () => Promise.resolve(JSON.parse(el.textContent)) });
};
"""


def main(out):
    html = open(SRC, encoding='utf-8').read()
    style = re.search(r'<style>(.*?)</style>', html, re.S).group(1)
    body = re.search(r'<body>(.*?)</body>', html, re.S).group(1)
    title = re.search(r'<title>(.*?)</title>', html, re.S).group(1)
    script = re.search(r'<script>(.*?)</script>', body, re.S).group(1)
    body_only = re.sub(r'<script>.*?</script>', '', body, flags=re.S).strip()

    blocks = []
    for name in DATA:
        raw = open(os.path.join(ROOT, 'data', '%s.json' % name), encoding='utf-8').read()
        json.loads(raw)                       # fail loudly on a truncated source
        # "</" can never appear in these payloads, but an unescaped one would
        # close the block early and silently truncate the data
        blocks.append('<script type="application/json" id="d-%s">%s</script>'
                      % (name, raw.replace('</', '<\\/')))

    out_html = ('<meta charset="utf-8">\n<title>%s</title>\n<style>\n%s\n</style>\n'
                '%s\n%s\n<script>\n%s\n%s\n</script>\n'
                % (title, style, body_only, '\n'.join(blocks), SHIM, script))
    open(out, 'w', encoding='utf-8').write(out_html)
    print('wrote %s  %.2f MB' % (out, os.path.getsize(out) / 1048576))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1
         else os.path.join(ROOT, 'ICD10-DRG-DCL-single-file.html'))
