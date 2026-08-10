/* Live browser checks for index.html: the six bugs fixed + the new reverse tab. */
process.env.NODE_PATH = require('child_process').execSync('npm root -g').toString().trim();
require('module').Module._initPaths();
const { chromium } = require('playwright');
const fs = require('fs'), os = require('os'), path = require('path');

/* the page writes store-only ZIPs, so entries can be read without inflate */
function unzip(buf){
  const files = {};
  for(let i = 0; i + 4 <= buf.length; ){
    if(buf.readUInt32LE(i) !== 0x04034b50){ i++; continue; }
    const size = buf.readUInt32LE(i+18), nlen = buf.readUInt16LE(i+26), elen = buf.readUInt16LE(i+28);
    const name = buf.slice(i+30, i+30+nlen).toString('utf8');
    const start = i + 30 + nlen + elen;
    files[name] = buf.slice(start, start + size);
    i = start + size;
  }
  return files;
}
function sheetRows(xml){
  return [...xml.matchAll(/<row[^>]*>(.*?)<\/row>/gs)].map(m =>
    [...m[1].matchAll(/<c[^>]*>(?:<is><t[^>]*>(.*?)<\/t><\/is>|<v>(.*?)<\/v>)<\/c>/gs)]
      .map(c => (c[1] !== undefined ? c[1] : c[2])
        .replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>')));
}

const BASE = process.argv[2] || 'http://127.0.0.1:8765/index.html';
let pass = 0, fail = 0;
const ok = (name, cond, extra='') => {
  if(cond){ pass++; console.log('  PASS ' + name); }
  else { fail++; console.log('  FAIL ' + name + (extra?'  -> '+extra:'')); }
};

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { const u = (m.location() && m.location().url) || '';
    if(m.type()==='error' && !/favicon/i.test(u + m.text())) errors.push('console: '+m.text()+' @'+u); });
  page.on('requestfailed', r => { if(!/favicon/i.test(r.url())) errors.push('req: '+r.url()); });

  await page.goto(BASE);
  await page.waitForFunction(() => typeof MAIN !== 'undefined' && MAIN.length > 0, null, { timeout: 30000 });

  // ---------- tab 1: any-key search ----------
  console.log('\n[tab 1] any-key search');
  const hitTexts = async () => page.$$eval('#hits .hit', els => els.map(e => e.textContent.trim()));

  await page.fill('#q', '440');
  await page.waitForTimeout(120);
  let h = await hitTexts();
  ok('"440" finds ICD J440 (substring, not just prefix)', h.some(t => t.includes('J440')), h.slice(0,3).join(' | '));
  ok('"440" finds no DRG group (none contains 440) instead of inventing one',
     !h.some(t => t.includes('DRG group')), h.slice(0,3).join(' | '));

  await page.fill('#q', 'pneumo');
  await page.waitForTimeout(120);
  h = await hitTexts();
  ok('"pneumo" matches descriptions', h.length > 0 && /pneumo/i.test(h.join(' ')), String(h.length));

  await page.fill('#q', 'J189');
  await page.waitForTimeout(120);
  h = await hitTexts();
  ok('exact code J189 ranks first', h[0] && h[0].includes('J189'), h[0]);

  await page.fill('#q', '155');
  await page.waitForTimeout(120);
  h = await hitTexts();
  // the point of any-key: prefix-only matching found 0155 but never 1155 / 2155
  ok('"155" finds groups 0155 AND 1155 AND 2155 (substring, zero-padded first)',
     ['0155','1155','2155'].every(g => h.some(t => t.includes(g + ' '))) && h[0].includes('0155'),
     h.filter(t=>t.includes('DRG group')).slice(0,5).join(' | '));

  await page.fill('#q', '');

  // ---------- tab 2: the add-code bugs ----------
  console.log('\n[tab 2] comorbid matrix');
  await page.click('#tabs button[data-tab="cmp"]');
  await page.waitForTimeout(200);

  const cols = () => page.$$eval('table.mx thead th .colcode', els => els.map(e => e.textContent.replace(/[▲▼]/g,'').trim()));

  // BUG 1: 5-6 char codes were silently dropped
  await page.click('#btnClearCodes');
  await page.fill('#cq', 'B1810');
  await page.waitForTimeout(200);
  await page.click('#chits .hit');
  await page.waitForTimeout(300);
  let c = await cols();
  ok('BUG1 5-char code B1810 can be added by clicking a suggestion', c.includes('B1810'), JSON.stringify(c));

  await page.fill('#cq', 'I70210');
  await page.waitForTimeout(200);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  c = await cols();
  ok('BUG1 6-char code I70210 can be added by typing + Enter', c.includes('I70210'), JSON.stringify(c));

  // BUG 2: dotted code split into the wrong column
  await page.click('#btnClearCodes');
  await page.waitForTimeout(150);
  await page.fill('#cq', 'J18.9');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  c = await cols();
  ok('BUG2 "J18.9" becomes J189 (not J18)', c.includes('J189') && !c.includes('J18'), JSON.stringify(c));

  // multiple codes at once, mixed shapes
  await page.click('#btnClearCodes');
  await page.waitForTimeout(150);
  await page.fill('#cq', 'N39.0, E11.9 B1810');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  c = await cols();
  ok('mixed list "N39.0, E11.9 B1810" adds all three',
     ['N390','E119','B1810'].every(x => c.includes(x)), JSON.stringify(c));

  // unreadable token is reported, not swallowed
  await page.fill('#cq', 'ZZTOP');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  const ignored = await page.$$eval('#chips .pill.missing', els => els.map(e => e.textContent.trim()));
  ok('unreadable token is reported instead of silently dropped', ignored.some(t => t.includes('ZZTOP')), JSON.stringify(ignored));

  // BUG 6: bare "X" used to match everything
  await page.fill('#cq', 'X');
  await page.waitForTimeout(250);
  const xhits = await page.$$eval('#chits .hit', els => els.length);
  ok('BUG6 bare "X" no longer matches all 7,219 codes', xhits === 0, 'hits=' + xhits);

  // wildcard still works
  await page.click('#btnClearCodes');
  await page.waitForTimeout(150);
  await page.fill('#cq', 'F102X');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  c = await cols();
  ok('wildcard F102X still expands', c.length >= 1 && c.every(x => x.startsWith('F102')), JSON.stringify(c).slice(0,120));

  // BUG 5: preset group set reports what it dropped
  await page.click('#btnPresetCodes');
  await page.waitForTimeout(300);
  await page.click('#btnPresetDcs');
  await page.waitForTimeout(600);
  const rowCount = await page.$$eval('table.mx tbody tr', els => els.length);
  const noteTxt = await page.$eval('#cmpview', el => el.textContent);
  ok('BUG5 preset shows 121 rows', rowCount === 121, 'rows=' + rowCount);
  ok('BUG5 the 2 empty groups are named on screen',
     noteTxt.includes('1457') && noteTxt.includes('1954') && noteTxt.includes('123'),
     noteTxt.includes('1457') + '/' + noteTxt.includes('1954'));

  // BUG 3: clicking the summary table header killed the matrix sort
  const firstRow = () => page.$eval('table.mx tbody tr td.dccell code', e => e.textContent.trim());
  await page.click('table.mx thead th[data-s="0"]');
  await page.waitForTimeout(400);
  const sortedTop = await firstRow();
  const arrowsBefore = await page.$$eval('table.mx thead th', els => els.filter(e => /[▲▼]/.test(e.textContent)).length);
  await page.$$eval('#cmpview .card:nth-of-type(1)', () => {});
  // the summary table is the second card; click one of its headers
  await page.click('#cmpview .card:last-of-type thead th:nth-child(2)');
  await page.waitForTimeout(400);
  const afterTop = await firstRow();
  const arrowsAfter = await page.$$eval('table.mx thead th', els => els.filter(e => /[▲▼]/.test(e.textContent)).length);
  ok('BUG3 summary-table header click does not disturb the matrix sort',
     sortedTop === afterTop && arrowsAfter === arrowsBefore,
     `${sortedTop}->${afterTop}, arrows ${arrowsBefore}->${arrowsAfter}`);

  // BUG 4: sortBy index left dangling after removing codes
  await page.click('#btnClearCodes');
  await page.waitForTimeout(150);
  await page.fill('#cq', 'J440 J441 N390');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  await page.click('table.mx thead th[data-s="2"]');   // sort by the 3rd code
  await page.waitForTimeout(300);
  await page.click('#chips .pill:last-of-type button[data-act="del"]');  // then delete it
  await page.waitForTimeout(400);
  const st = await page.evaluate(() => ({ by: CMP.sortBy, dir: CMP.sortDir }));
  const arrows = await page.$$eval('table.mx thead th', els => els.filter(e => /[▲▼]/.test(e.textContent)).length);
  ok('BUG4 sort falls back to DRG group when its column is removed',
     st.by === 'dc' && arrows === 1, JSON.stringify(st) + ' arrows=' + arrows);

  // ---------- tab 3: the reverse view ----------
  console.log('\n[tab 3] reverse view (new)');
  await page.click('#tabs button[data-tab="rev"]');
  await page.waitForTimeout(300);
  await page.fill('#rq', '0155');
  await page.waitForTimeout(250);
  await page.click('#rhits .hit');
  await page.waitForTimeout(600);

  const revRows = () => page.$$eval('#revview tbody tr', els => els.map(tr => {
    const td = tr.querySelectorAll('td');
    return { dcl: td[0].textContent.trim(), code: td[1].textContent.trim(), desc: td[2].textContent.trim() };
  }));

  const head = await page.$eval('#revview h3', e => e.textContent.replace(/\s+/g,' ').trim());
  ok('group header shows 0155', head.includes('0155'), head);

  // หมอเกน's worked example: 0155 -> J440 = 2, J441 = 1
  const levelBtns = await page.$$eval('#rlevels button', els => els.map(e => e.textContent.replace(/\s+/g,' ').trim()));
  ok('level counts match the data (DCL5=3, DCL4=18, DCL3=286)',
     levelBtns[0].includes('(3)') && levelBtns[1].includes('(18)') && levelBtns[2].includes('(286)'),
     JSON.stringify(levelBtns));

  // enable all levels so J440/J441 (DCL 2 and 1) show up
  await page.click('#rlevels button[data-lv="2"]');
  await page.waitForTimeout(300);
  await page.click('#rlevels button[data-lv="1"]');
  await page.waitForTimeout(400);
  await page.fill('#rFilter', 'J44');
  await page.waitForTimeout(500);
  const r = await revRows();
  const j440 = r.find(x => x.code === 'J440'), j441 = r.find(x => x.code === 'J441');
  ok('example: J440 -> DCL 2 in group 0155', j440 && j440.dcl === '2', JSON.stringify(j440));
  ok('example: J441 -> DCL 1 in group 0155', j441 && j441.dcl === '1', JSON.stringify(j441));
  ok('description column is filled', j440 && j440.desc.length > 3, j440 && j440.desc);

  // any-key filter on description
  await page.fill('#rFilter', 'cirrhosis');
  await page.waitForTimeout(500);
  const r2 = await revRows();
  ok('filter matches descriptions too', r2.length > 0 && /cirrhosis/i.test(r2.map(x=>x.desc).join(' ')), 'rows=' + r2.length);

  // paging
  await page.fill('#rFilter', '');
  await page.waitForTimeout(600);
  const shownFirst = await page.$$eval('#revview tbody tr', els => els.length);
  ok('long list is paged at 300 rows, not dumped whole', shownFirst === 300, 'rows=' + shownFirst);
  await page.click('#btnRevMore');
  await page.waitForTimeout(500);
  const shownMore = await page.$$eval('#revview tbody tr', els => els.length);
  ok('"show more" adds another page', shownMore === 600, 'rows=' + shownMore);

  // total for 0155 = 5,135 contributors
  const totalTxt = await page.$eval('#revview p.muted', e => e.textContent.replace(/\s+/g,' '));
  ok('total contributor count = 5,135', totalTxt.includes('5,135'), totalTxt.slice(0,160));

  // age-split codes land in two different groups; showing only the >= side
  // silently understated 578 of the rows in group 0155 alone
  await page.evaluate(() => { REV.levels = new Set([1,2,3,4,5]); showRev(); });
  await page.waitForTimeout(400);
  await page.fill('#rFilter', 'A000');
  await page.waitForTimeout(500);
  const splitCell = await page.$eval('#revview tbody tr td:nth-child(4)', e => e.textContent.replace(/\s+/g,' ').trim());
  ok('age-split code shows BOTH PDx groups with the cutoff',
     splitCell.includes('0658') && splitCell.includes('0657') && splitCell.includes('10'), splitCell);

  await page.fill('#rFilter', 'D630');
  await page.waitForTimeout(500);
  const nonPdx = await page.$eval('#revview tbody tr td:nth-child(4)', e => e.textContent.trim());
  ok('comorbid-only code is labelled as not usable as PDx', nonPdx.includes('ไม่ได้'), nonPdx);

  // the .xlsx really opens: right entries, right row count, Thai + leading zero intact
  await page.fill('#rFilter', '');
  await page.waitForTimeout(700);
  const label = await page.$eval('#btnXlsxRev', e => e.textContent.trim());
  ok('export button states how many rows it will write', /5,135/.test(label), label);
  const [dl] = await Promise.all([ page.waitForEvent('download'), page.click('#btnXlsxRev') ]);
  const xp = path.join(os.tmpdir(), 'icd_test_' + Date.now() + '.xlsx');
  await dl.saveAs(xp);
  const z = unzip(fs.readFileSync(xp));
  ok('xlsx has the 5 OPC parts', Object.keys(z).length === 5, Object.keys(z).join(','));
  const xrows = sheetRows(z['xl/worksheets/sheet1.xml'].toString('utf8'));
  const nOnScreen = await page.evaluate(() => REVROWS.length);
  ok('xlsx row count == filtered set + header', xrows.length === nOnScreen + 1, xrows.length + ' vs ' + (nOnScreen+1));
  ok('xlsx keeps the leading zero on the DRG group', xrows[1][0] === '0155', xrows[1][0]);
  ok('xlsx Thai header intact', xrows[0][4] === 'คำอธิบาย' && xrows[0][5].includes('PDx'), JSON.stringify(xrows[0]));
  const a000 = xrows.find(r => r[3] === 'A000');
  ok('xlsx carries both age groups too', a000 && /0658.*0657/.test(a000[5]), a000 && a000[5]);
  fs.unlinkSync(xp);
  await page.evaluate(() => { REV.levels = new Set([5,4,3]); REV.limit = REV.PAGE; showRev(); });
  await page.waitForTimeout(500);

  // group with no DCL data at all
  await page.evaluate(() => { location.hash = 'rev/1457'; });
  await page.waitForTimeout(600);
  const empty = await page.$eval('#revview', e => e.textContent.replace(/\s+/g,' ').trim());
  ok('group 1457 explains why it is empty rather than showing a blank table',
     empty.includes('ไม่มีรหัสโรคใดให้ค่า DCL'), empty.slice(0,140));

  // deep link straight into the tab (cold-ish load)
  await page.goto(BASE + '#rev/0155');
  await page.waitForFunction(() => typeof MAIN !== 'undefined' && MAIN.length > 0, null, { timeout: 30000 });
  await page.waitForTimeout(900);
  const deepHead = await page.$eval('#revview h3', e => e.textContent.replace(/\s+/g,' ').trim());
  const paneVisible = await page.$eval('#pane-rev', e => !e.hidden);
  ok('deep link #rev/0155 opens the tab on a cold load', paneVisible && deepHead.includes('0155'), deepHead);

  console.log('\nJS errors: ' + (errors.length ? errors.join(' || ') : 'none'));
  ok('no uncaught JS errors', errors.length === 0);

  console.log(`\n==== ${pass} passed, ${fail} failed ====`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
