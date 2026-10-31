
import os, pymupdf
ROOT = r'C:\Projects\停车场充电桩优化方案'
outdir = os.path.join(ROOT, 'research', 'round6_20261031', 'c_paper', 'render_png')
os.makedirs(outdir, exist_ok=True)
for tag, p, picks in (('MAIN', r'research\round6_20261031\c_paper\round6_rev2_draft.pdf', [19, 24, 39, 51]),
                      ('SI', r'research\round6_20261031\c_paper\round6_rev2_supplement.pdf', [1, 4, 5, 7])):
    doc = pymupdf.open(os.path.join(ROOT, p))
    blank, over = [], []
    for i, page in enumerate(doc):
        r = page.rect
        pix = page.get_pixmap(dpi=60)
        s = pix.samples; n = max(1, len(s)//3)
        ink = sum(1 for b in range(0, len(s), 3*5) if s[b] < 240 or s[b+1] < 240 or s[b+2] < 240)
        if ink / (n/5.0) < 0.002: blank.append(i+1)
        for blk in page.get_text('blocks'):
            x0, y0, x1, y1, t = blk[0], blk[1], blk[2], blk[3], blk[4].strip()
            if y0 > r.height - 60: continue
            if x0 < 40 or x1 > r.width - 40 or y1 > r.height - 30 or y0 < 20:
                over.append((i+1, round(x0), round(x1), round(y1), t[:28]))
    print(tag, 'pages', doc.page_count, 'blank', blank, 'overflow', len(over), over[:4])
    for pno in picks:
        if pno <= doc.page_count:
            doc[pno-1].get_pixmap(dpi=110).save(os.path.join(outdir, '%s_p%02d.png' % (tag, pno)))
print('png dir', outdir)
