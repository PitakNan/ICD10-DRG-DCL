"""Mirror of the in-page XLSX writer, to prove the byte layout opens in Excel."""
import struct, zlib, io


def col_name(n):
    s = ''
    n += 1
    while n > 0:
        m = (n - 1) % 26
        s = chr(65 + m) + s
        n = (n - m - 1) // 26
    return s


def xe(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def sheet_xml(rows):
    out = []
    for i, r in enumerate(rows):
        cells = []
        for j, v in enumerate(r):
            ref = col_name(j) + str(i + 1)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append('<c r="%s"><v>%s</v></c>' % (ref, v))
            else:
                cells.append('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                             % (ref, xe('' if v is None else v)))
        out.append('<row r="%d">%s</row>' % (i + 1, ''.join(cells)))
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org'
            '/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % ''.join(out))


def build(rows):
    files = [
        ('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'),
        ('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
        ('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="DCL" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        ('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'),
        ('xl/worksheets/sheet1.xml', sheet_xml(rows)),
    ]
    chunks, central, off = [], [], 0
    for name, content in files:
        data = content.encode('utf-8')
        n = name.encode('utf-8')
        crc = zlib.crc32(data) & 0xFFFFFFFF
        lh = bytearray(30)
        struct.pack_into('<IHHHHHIIIHH', lh, 0, 0x04034b50, 20, 0x0800, 0, 0, 0,
                         crc, len(data), len(data), len(n), 0)
        chunks += [bytes(lh), n, data]
        ch = bytearray(46)
        struct.pack_into('<IHHHHHHIIIHHHHHII', ch, 0, 0x02014b50, 20, 20, 0x0800, 0, 0, 0,
                         crc, len(data), len(data), len(n), 0, 0, 0, 0, 0, off)
        central += [bytes(ch), n]
        off += 30 + len(n) + len(data)
    cd = b''.join(central)
    eo = bytearray(22)
    struct.pack_into('<IHHHHIIH', eo, 0, 0x06054b50, 0, 0, len(files), len(files),
                     len(cd), off, 0)
    return b''.join(chunks) + cd + bytes(eo)


if __name__ == '__main__':
    rows = [['DC', 'DC name', 'DCL', 'ICD-10'],
            ['0455', 'Chronic obstructive pulmonary disease', 3, 'J430'],
            ['0455', 'ทดสอบภาษาไทย & <xml>', 2, 'J440']]
    blob = build(rows)
    open('test.xlsx', 'wb').write(blob)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(blob))
    ws = wb.active
    print('sheet:', ws.title, 'dims:', ws.dimensions)
    for r in ws.iter_rows(values_only=True):
        print(r)
    print('OK - openpyxl parsed the file written by the same byte layout as the page')
