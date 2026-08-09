"""TDS6307 driver v2: layout-independent Unicode typing + clipboard result read."""
import ctypes, ctypes.wintypes as wt, time, os, subprocess
import win32gui, win32ui, win32con, win32clipboard
from PIL import Image

u32 = ctypes.WinDLL('user32', use_last_error=True)
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
VK_BACK, VK_END, VK_CONTROL, VK_HOME = 0x08, 0x23, 0x11, 0x24

APPDIR = r'D:\Download Line\2026-08-09 Project ICD10\TDS6307\TDS6307'
APP = os.path.join(APPDIR, 'TDS6307.EXE')

C = dict(AGE=(62, 83), AGEDAY=(158, 83), SEX=(247, 83), DISC=(316, 83), WT=(465, 83),
         LOSD=(588, 83), PDX=(799, 83), FIND=(485, 314), CLEAR=(245, 313),
         DETAIL=(729, 313), BACK=(489, 607), TEXT=(492, 269))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wt.WORD), ('wScan', wt.WORD), ('dwFlags', wt.DWORD),
                ('time', wt.DWORD), ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wt.LONG), ('dy', wt.LONG), ('mouseData', wt.DWORD),
                ('dwFlags', wt.DWORD), ('time', wt.DWORD),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wt.DWORD), ('wParamL', wt.WORD), ('wParamH', wt.WORD)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', wt.DWORD), ('u', _U)]


def send_unicode(ch):
    for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
        inp = INPUT(type=1)
        inp.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
        n = u32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        if not n:
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.004)


class Grouper:
    def __init__(self, launch=True):
        if launch:
            subprocess.Popen([APP], cwd=APPDIR)
        self.hwnd = None
        for _ in range(30):
            time.sleep(1)
            self.hwnd = self._find()
            if self.hwnd:
                break
        if not self.hwnd:
            raise RuntimeError('grouper window not found')
        self.focus()
        kids = []
        win32gui.EnumChildWindows(self.hwnd, lambda c, _: kids.append(c), None)
        self.ox, self.oy = win32gui.ClientToScreen(kids[0] if kids else self.hwnd, (0, 0))
        self.use_english()

    @staticmethod
    def _find():
        found = []

        def cb(h, _):
            if 'DRG Seeker' in win32gui.GetWindowText(h):
                found.append(h)
        win32gui.EnumWindows(cb, None)
        return found[0] if found else None

    def focus(self):
        try:
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass
        time.sleep(0.3)

    def click(self, name, settle=0.05):
        x, y = C[name]
        u32.SetCursorPos(self.ox + x, self.oy + y)
        time.sleep(0.015)
        u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.015)
        u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(settle)

    kd = 0.030   # per-keystroke delay; VFP silently drops keys sent faster

    def key(self, vk, n=1, ctrl=False, shift=False):
        if ctrl:
            u32.keybd_event(VK_CONTROL, 0, 0, 0)
            time.sleep(self.kd)
        if shift:
            u32.keybd_event(0x10, 0, 0, 0)
            time.sleep(self.kd)
        for _ in range(n):
            u32.keybd_event(vk, 0, 0, 0)
            time.sleep(self.kd)
            u32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(self.kd)
        if shift:
            u32.keybd_event(0x10, 0, KEYEVENTF_KEYUP, 0)
        if ctrl:
            u32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(self.kd)

    def use_english(self):
        """Force the grouper's input language to English so VK codes map to ASCII.

        The Thai (Kedmanee) layout turns every letter AND digit key into a Thai
        character, which the numeric/code input masks silently reject.
        """
        WM_INPUTLANGCHANGEREQUEST = 0x0050
        n = u32.GetKeyboardLayoutList(0, None)
        arr = (ctypes.c_void_p * n)()
        u32.GetKeyboardLayoutList(n, arr)
        en = [h for h in arr if (h & 0xFFFF) == 0x0409]
        if not en:
            raise RuntimeError('no English keyboard layout installed')
        win32gui.PostMessage(self.hwnd, WM_INPUTLANGCHANGEREQUEST, 0, en[0])
        time.sleep(0.4)

    def type(self, s):
        """Type ASCII via virtual-key codes (layout is forced to English)."""
        for ch in s:
            if ch.isdigit():
                self.key(ord(ch))
            elif ch.isalpha():
                self.key(ord(ch.upper()), shift=True)
            else:
                send_unicode(ch)

    def dblclick(self, name, settle=0.08):
        x, y = C[name]
        u32.SetCursorPos(self.ox + x, self.oy + y)
        time.sleep(0.02)
        for _ in range(2):
            u32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.02)
            u32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.03)
        time.sleep(settle)

    def set_field(self, name, val, mode='dbl'):
        """Replace a field's contents.

        Double-click selects the whole (space-free) value and typing overwrites
        it; End+Backspace does NOT work reliably here -- VFP drops the keys.
        """
        if mode == 'dbl':
            self.dblclick(name)
        else:
            self.click(name, settle=0.08)
            self.key(0x41, ctrl=True)
        self.type(val)

    def shot(self, out=None):
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        w, h = r - l, b - t
        hdc = win32gui.GetWindowDC(self.hwnd)
        src = win32ui.CreateDCFromHandle(hdc)
        dst = src.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(src, w, h)
        dst.SelectObject(bmp)
        ctypes.windll.user32.PrintWindow(self.hwnd, dst.GetSafeHdc(), 2)
        info = bmp.GetInfo()
        im = Image.frombuffer('RGB', (info['bmWidth'], info['bmHeight']),
                              bmp.GetBitmapBits(True), 'raw', 'BGRX', 0, 1)
        win32gui.DeleteObject(bmp.GetHandle())
        dst.DeleteDC(); src.DeleteDC(); win32gui.ReleaseDC(self.hwnd, hdc)
        if out:
            im.save(out)
        return im

    def setup(self, age='70', sex='1', disc='1', wt='70', losd='3'):
        for f, v in [('AGE', age), ('SEX', sex), ('DISC', disc), ('WT', wt), ('LOSD', losd)]:
            self.set_field(f, v)

    def clipboard(self):
        for _ in range(6):
            try:
                win32clipboard.OpenClipboard()
                try:
                    return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                time.sleep(0.05)
        return None


if __name__ == '__main__':
    g = Grouper()
    print('hwnd', hex(g.hwnd), 'origin', (g.ox, g.oy))
    g.setup()
    g.set_field('PDX', 'J440')
    g.shot('c2_typed.png')
    g.click('FIND', settle=0.5)
    g.shot('c2_result.png')
    # try reading the detail page through the clipboard
    g.click('DETAIL', settle=0.6)
    g.shot('c2_detail.png')
    g.click('TEXT')
    g.key(0x41, ctrl=True)
    g.key(0x43, ctrl=True)
    txt = g.clipboard()
    print('CLIPBOARD >>>', repr(txt)[:800])
    g.click('BACK', settle=0.4)
    g.shot('c2_back.png')
    print('DONE')
