import struct, os, sys

BASE = r'D:\Download Line\2026-08-09 Project ICD10\TDS6307\TDS6307'

def read_header(filename):
    with open(filename, 'rb') as f:
        header = f.read(32)
        num_records = struct.unpack('<I', header[4:8])[0]
        header_size = struct.unpack('<H', header[8:10])[0]
        record_size = struct.unpack('<H', header[10:12])[0]
        fields = []
        while True:
            fd = f.read(32)
            if fd[0] == 0x0D:
                break
            name = fd[0:11].split(b'\x00')[0].decode('ascii', 'replace')
            ftype = chr(fd[11])
            flen = fd[16]
            dec = fd[17]
            fields.append((name, ftype, flen, dec))
    return num_records, header_size, record_size, fields

def read_dbf(filename, limit=None):
    n, hs, rs, fields = read_header(filename)
    rows = []
    with open(filename, 'rb') as f:
        f.seek(hs)
        for i in range(n):
            rec = f.read(rs)
            if not rec or len(rec) < rs:
                break
            if rec[0] == 0x2A:
                continue
            row = {}
            off = 1
            for name, ftype, flen, dec in fields:
                raw = rec[off:off+flen]
                if ftype == 'L':
                    val = raw.decode('latin1').strip()
                else:
                    val = raw.decode('cp874', 'replace').strip()
                row[name] = val
                off += flen
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    return fields, rows

if __name__ == '__main__':
    for fn in sorted(os.listdir(BASE)):
        if fn.lower().endswith('.dbf'):
            p = os.path.join(BASE, fn)
            n, hs, rs, fields = read_header(p)
            print(f'=== {fn}  records={n} recsize={rs}')
            for f_ in fields:
                print('   ', f_)
