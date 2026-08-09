"""Fold site/index.html + site/data/*.json into one self-contained page."""
import json, os, re

SRC = 'site/index.html'
OUT = 'artifact.html'
DATA = ['main', 'drg', 'desc', 'dcl']


def main():
    html = open(SRC, encoding='utf-8').read()
    style = re.search(r'<style>(.*?)</style>', html, re.S).group(1)
    body = re.search(r'<body>(.*?)</body>', html, re.S).group(1)
    title = re.search(r'<title>(.*?)</title>', html, re.S).group(1)
    script = re.search(r'<script>(.*?)</script>', body, re.S).group(1)
    body_only = re.sub(r'<script>.*?</script>', '', body, flags=re.S).strip()

    blocks = []
    for name in DATA:
        raw = open('site/data/%s.json' % name, encoding='utf-8').read()
        # </script> can never appear in these payloads, but guard anyway
        raw = raw.replace('</', '<\\/')
        blocks.append('<script type="application/json" id="d-%s">%s</script>' % (name, raw))

    # The charset declaration must land inside the first 1024 bytes or a host that
    # serves the file without a charset header renders the Thai text as mojibake.
    out = ('<meta charset="utf-8">\n<title>%s</title>\n<style>\n%s\n</style>\n'
           '%s\n%s\n<script>\n%s\n</script>\n'
           % (title, style, body_only, '\n'.join(blocks), script))
    open(OUT, 'w', encoding='utf-8').write(out)
    print('wrote %s  %.2f MB' % (OUT, os.path.getsize(OUT) / 1048576))


if __name__ == '__main__':
    main()
