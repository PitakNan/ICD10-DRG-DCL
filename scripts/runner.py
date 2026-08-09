"""Fire ICD-10 codes through TDS6307 as PDx-only cases and record the DRG.

Reads each result from the grouper's own detail page via the clipboard, so the
value is exact text -- no OCR. Every iteration re-reads the PDx the grouper
echoes back and refuses to record a row whose echo does not match the request.
Results are appended to results.csv after each code, so a run can resume.
"""
import ctypes, csv, os, re, sys, time
import win32process, win32gui
from real2 import Grouper, u32, KEYEVENTF_KEYUP
import dbf as D

OUT = 'results.csv'
# the detail page prints the accepted PDx on the line after the label:
#    Principal Diagnosis:-
#      J440: Chronic obstructive pulmonary disease with ...
RE_PDX = re.compile(r'Principal Diagnosis:-\s*(?:\r?\n\s*)?([A-Z][A-Z0-9]*)\s*:')
RE_DRG = re.compile(r'====>\s*DRG\s+(\d+)\s*(?:\((.*?)\))?')
RE_AGE = re.compile(r'Age\s*=\s*(\d+)')
RE_SEX = re.compile(r'Sex\s*=\s*(\S*)')


def force_english(hwnd):
    tid, _ = win32process.GetWindowThreadProcessId(hwnd)
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    u32.AttachThreadInput(me, tid, True)
    n = u32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.c_void_p * n)()
    u32.GetKeyboardLayoutList(n, arr)
    en = [h for h in arr if (h & 0xFFFF) == 0x0409]
    if not en:
        raise RuntimeError('no English keyboard layout installed')
    u32.ActivateKeyboardLayout(ctypes.c_void_p(en[0]), 0)
    u32.AttachThreadInput(me, tid, False)


def kill_app():
    import subprocess
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    'Get-Process TDS6307 -ErrorAction SilentlyContinue | '
                    'ForEach-Object { Stop-Process -Id $_.Id -Force }'],
                   capture_output=True)
    time.sleep(1.5)


def pick_targets(n_per_pdc=3):
    _, i10 = D.read_dbf('data/c63i10.dbf')
    acc = [r for r in i10 if r['ACCPDX'] == 'Y']
    groups = {}
    for r in acc:
        groups.setdefault(r['PDC'], []).append(r)
    targets = []
    for pdc, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r['CODE'])
        idx = sorted({0, len(rows) // 2, len(rows) - 1})[:n_per_pdc]
        for i in idx:
            targets.append((rows[i]['CODE'], pdc, rows[i]['MDC']))
    return targets


class Session:
    """Holds the constant patient context; PDx is the only thing that varies."""

    AGE, SEX, DISC, WT, LOSD = '70', '1', '1', '70', '3'

    def __init__(self, verify=True):
        self.g = Grouper()
        force_english(self.g.hwnd)
        self.set_context()
        if verify:
            self.verify_context()

    def set_context(self):
        g = self.g
        force_english(g.hwnd)
        for f, v in [('AGE', self.AGE), ('SEX', self.SEX), ('DISC', self.DISC),
                     ('WT', self.WT), ('LOSD', self.LOSD)]:
            g.set_field(f, v)

    def verify_context(self):
        """Fail loudly if the constant fields did not take -- a blank Sex or Age
        silently changes which DC the grouper picks."""
        for attempt in range(3):
            _, _, _, txt = self.query('J440')
            age, sex = RE_AGE.search(txt), RE_SEX.search(txt)
            if age and age.group(1) == self.AGE and sex and sex.group(1) == self.SEX:
                print('context OK: age=%s sex=%s' % (age.group(1), sex.group(1)))
                return
            print('context attempt %d: age=%r sex=%r -- retrying' %
                  (attempt + 1, age and age.group(1), sex and sex.group(1)))
            self.set_context()
        raise RuntimeError('could not set the constant patient fields')

    def query(self, code, mode='dbl'):
        g = self.g
        # the layout reverts to Thai on its own, so re-assert it every time
        force_english(g.hwnd)
        g.set_field('PDX', code, mode=mode)
        g.click('FIND', settle=0.25)
        g.click('DETAIL', settle=0.25)
        g.click('TEXT')
        g.key(0x41, ctrl=True)
        g.key(0x43, ctrl=True)
        txt = g.clipboard() or ''
        g.click('BACK', settle=0.20)
        m_pdx, m_drg = RE_PDX.search(txt), RE_DRG.search(txt)
        return (m_pdx.group(1) if m_pdx else None,
                m_drg.group(1) if m_drg else None,
                (m_drg.group(2) or '').strip() if m_drg else '',
                txt)


def main():
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    targets = pick_targets(n_per)
    done = set()
    if os.path.exists(OUT):
        with open(OUT, newline='', encoding='utf-8') as f:
            done = {r['code'] for r in csv.DictReader(f) if r.get('drg')}
    todo = [t for t in targets if t[0] not in done]
    print('targets %d, already done %d, to run %d' % (len(targets), len(done), len(todo)))

    s = Session()
    new = os.path.getsize(OUT) == 0 if os.path.exists(OUT) else True
    f = open(OUT, 'a', newline='', encoding='utf-8')
    w = csv.writer(f)
    if new:
        w.writerow(['code', 'pdc', 'mdc', 'echo_pdx', 'drg', 'drgname', 'status'])
    t0 = time.time()
    bad = recovered = 0

    def attempt(code, mode):
        echo, drg, name, txt = s.query(code, mode=mode)
        return (echo, drg, name, txt) if (echo == code and drg) else None

    for i, (code, pdc, mdc) in enumerate(todo, 1):
        res = attempt(code, 'dbl') or attempt(code, 'ctrla')
        status = 'ok'
        if not res:
            # the form drifts out of a usable state after a while; reset it
            s.g.click('CLEAR', settle=0.3)
            s.set_context()
            res = attempt(code, 'dbl')
            status = 'ok-reset'
            if not res:
                kill_app()
                s = Session(verify=True)
                res = attempt(code, 'dbl')
                status = 'ok-restart'
            if res:
                recovered += 1
        if res:
            echo, drg, name, _ = res
        else:
            echo, drg, name, status = None, None, '', 'FAILED'
            bad += 1
        w.writerow([code, pdc, mdc, echo, drg, name, status])
        f.flush()
        if i % 25 == 0 or i == len(todo):
            el = time.time() - t0
            print('%d/%d  %.0fs  %.2fs/code  recovered=%d failed=%d  last %s->%s' %
                  (i, len(todo), el, el / i, recovered, bad, code, drg), flush=True)
    f.close()
    print('DONE recovered=%d failed=%d' % (recovered, bad))


if __name__ == '__main__':
    main()
