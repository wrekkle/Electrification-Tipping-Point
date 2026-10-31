
import fitz, re, html, os, json
base = os.path.join(r"C:\Projects\停车场充电桩优化方案","research","official_data_20261031","identification_20261031")
raw = os.path.join(base,"raw"); txt = os.path.join(base,"raw_text"); os.makedirs(txt, exist_ok=True)
def strip_html(s):
    s = re.sub(r"<script.*?</script>|<style.*?</style>"," ",s,flags=re.S|re.I)
    s = re.sub(r"<[^>]+>","\n",s); return html.unescape(s)
for fn in ["t28_ly_charging_infra_2026.pdf","t28_audit_charging_parking.pdf"]:
    doc = fitz.open(os.path.join(raw,fn))
    t = "".join("\n===== PDF PAGE %d =====\n"%i + p.get_text() for i,p in enumerate(doc))
    open(os.path.join(txt, fn.replace(".pdf",".txt")),"w",encoding="utf-8").write(t)
    print("##",fn,"pages",doc.page_count,"chars",len(t))
    for kw in ["15,328","130,278","8.5","市售比","市佔","使用率","充電專用","1%以上","燃油"]:
        ms=list(re.finditer(re.escape(kw), t))[:2]
        for m in ms:
            print("  ",kw,"|",t[max(0,m.start()-130):m.start()+170].replace("\n"," / ")[:320])
for fn in ["t28_ndc_charging_news.html","t28_moenv_iea_gevo2025.html"]:
    s = strip_html(open(os.path.join(raw,fn),encoding="utf-8",errors="replace").read())
    lines=[l.strip() for l in s.splitlines() if l.strip()]
    open(os.path.join(txt, fn.replace(".html",".txt")),"w",encoding="utf-8").write("\n".join(lines))
    print("##",fn,"lines",len(lines))
    for kw in ["萬槍","充電","市售","佔","比例","電動車"]:
        for h in [l for l in lines if kw in l][:4]: print("  ",kw,"|",h[:250])
