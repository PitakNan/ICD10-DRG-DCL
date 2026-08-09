"""One-off probe: fire the 15 age-split-family PDC codes at two ages (5 and 70)
to find out which DC each side of the split actually resolves to.

Writes age_probe.csv with columns: pdc, code, age, drg, drgname, status
"""
import csv, sys, time
from real2 import Grouper, u32, KEYEVENTF_KEYUP
import win32process

RE = None
import re
RE_PDX = re.compile(r'Principal Diagnosis:-\s*(?:\r?\n\s*)?([A-Z][A-Z0-9]*)\s*:')
RE_DRG = re.compile(r'====>\s*DRG\s+(\d+)\s*(?:\((.*?)\))?')
RE_AGE = re.compile(r'Age\s*=\s*(\d+)')
RE_SEX = re.compile(r'Sex\s*=\s*(\S*)')

TARGETS = [
    ('11A', 'I120'), ('11J', 'N170'), ('2A', 'A185'),
    ('21A', 'S010'), ('21B', 'T780'), ('21C', 'R502'),
    ('8P', 'M2413'), ('8Q', 'M220'),
    ('9G', 'A46'), ('9H', 'S000'),
    ('6G', 'A000'), ('6N', 'K522'), ('6H', 'B378'), ('6L', 'B462'), ('6M', 'K20'),
]

OUT = 'age_probe.csv'


def force_english(hwnd):
    import ctypes
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


class Session:
    def __init__(self, age):
        self.age = age
        self.g = Grouper()
        force_english(self.g.hwnd)
        self.set_context()

    def set_context(self):
        g = self.g
        force_english(g.hwnd)
        for f, v in [('AGE', self.age), ('SEX', '1'), ('DISC', '1'),
                     ('WT', '70'), ('LOSD', '3')]:
            g.set_field(f, v)

    def verify_context(self):
        for attempt in range(3):
            _, _, _, txt = self.query('J440')
            age, sex = RE_AGE.search(txt), RE_SEX.search(txt)
            if age and age.group(1) == self.age and sex and sex.group(1) == '1':
                print('context OK: age=%s sex=%s' % (age.group(1), sex.group(1)), flush=True)
                return
            print('context attempt %d: age=%r sex=%r -- retrying' %
                  (attempt + 1, age and age.group(1), sex and sex.group(1)), flush=True)
            self.set_context()
        raise RuntimeError('could not set the constant patient fields for age=%s' % self.age)

    def query(self, code, mode='dbl'):
        g = self.g
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
                (m_drg.group(2) or '').strip() if m_drg else '', txt)


def kill_app():
    import subprocess, time as _t
    subprocess.run(['powershell', '-NoProfile', '-Command',
                    'Get-Process TDS6307 -ErrorAction SilentlyContinue | '
                    'ForEach-Object { Stop-Process -Id $_.Id -Force }'],
                   capture_output=True)
    _t.sleep(1.5)


def run_age(age, w):
    kill_app()
    s = Session(age)
    s.verify_context()
    for pdc, code in TARGETS:
        echo, drg, name, txt = s.query(code, mode='dbl')
        status = 'ok' if (echo == code and drg) else 'FAILED'
        if status == 'FAILED':
            echo, drg, name, txt = s.query(code, mode='ctrla')
            status = 'ok-retry' if (echo == code and drg) else 'FAILED'
        print(age, pdc, code, '->', drg, name, status, flush=True)
        w.writerow([pdc, code, age, drg, name, status])
        f.flush()


if __name__ == '__main__':
    f = open(OUT, 'w', newline='', encoding='utf-8')
    w = csv.writer(f)
    w.writerow(['pdc', 'code', 'age', 'drg', 'drgname', 'status'])
    run_age('5', w)
    run_age('70', w)
    f.close()
    kill_app()
    print('DONE ->', OUT)
