from pathlib import Path
from zipfile import ZipFile
from lxml import etree
import json
SOURCE=Path(__file__).resolve().parents[2] / 'main_paper' / 'Electrification tipping point_manuscript 202603submit.docx'
OUT=Path(__file__).resolve().parent
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
def tag(x): return etree.QName(x).localname
def tx(x):
    t=tag(x)
    if t in ('t','delText'): return x.text or ''
    if t.endswith('Pr'): return ''
    if t in ('tab','br','cr'): return ' '
    if t=='f': return '\\frac{'+''.join(tx(c) for c in x if tag(c)=='num')+'}{'+''.join(tx(c) for c in x if tag(c)=='den')+'}'
    if t in ('sSub','sSup','sSubSup'):
        e=''.join(tx(c) for c in x if tag(c)=='e')
        sub=''.join(tx(c) for c in x if tag(c)=='sub')
        sup=''.join(tx(c) for c in x if tag(c)=='sup')
        return e+('_{'+sub+'}' if sub else '')+('^{'+sup+'}' if sup else '')
    if t=='oMath': return '$'+''.join(tx(c) for c in x)+'$'
    return ''.join(tx(c) for c in x)
with ZipFile(SOURCE) as z:
    root=etree.fromstring(z.read('word/document.xml'))
    ps=root.xpath('//w:body//w:p',namespaces=NS)
    records=[{'paragraph':i+1,'text':tx(p)} for i,p in enumerate(ps) if tx(p).strip()]
    (OUT/'manuscript_extracted.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'manuscript_extracted.txt').write_text('\n\n'.join('[P%04d] '%r['paragraph']+r['text'] for r in records),encoding='utf-8')
    (OUT/'equations.xml').write_text('\n'.join(etree.tostring(x,encoding='unicode',pretty_print=True) for x in root.xpath('//m:oMath',namespaces=NS)),encoding='utf-8')
    for n in z.namelist():
        if n.startswith('word/media/'):
            (OUT/Path(n).name).write_bytes(z.read(n))
    from PIL import Image
    print(json.dumps({'paragraphs':len(records),'equations':len(root.xpath('//m:oMath',namespaces=NS)),'images':[(p.name,Image.open(p).size) for p in OUT.glob('image*.png')]},ensure_ascii=False))
