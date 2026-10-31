from pathlib import Path
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json, hashlib
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[2] / 'papers' / 'electrification-math'
ROOT.mkdir(parents=True,exist_ok=True)
PAPERS=[
 {'id':'M01','title':'Impact of Server Capability on Pooling Configuration in Stochastic Service Systems','filename':'M01_pooling-configuration_POM2026.pdf','urls':['https://journals.sagepub.com/doi/pdf/10.1177/10591478261417819'],'version':'Published article'},
 {'id':'M02','title':'Robust satisficing newsvendor problem','filename':'M02_robust-satisficing-newsvendor_author-preprint.pdf','urls':['https://papers.ssrn.com/sol3/Delivery.cfm/4506630.pdf?abstractid=4506630'],'version':'Author preprint; journal version 2026'},
 {'id':'M03','title':'Confidence Sets for the Sample Average Approximation of Stochastic Discrete Optimization Problems','filename':'M03_confidence-sets-stochastic-discrete-optimization_LEM2026-09.pdf','urls':['https://www.lem.sssup.it/WPLem/files/2026-09.pdf','https://www.econstor.eu/bitstream/10419/339276/1/1965623980.pdf'],'version':'LEM Working Paper 2026/09'},
 {'id':'M04','title':'On the Relevance of Incorporating Decision Dependence in Distributional Ambiguity','filename':'M04_decision-dependent-distributional-ambiguity_arxiv2609.33926v2.pdf','urls':['https://arxiv.org/pdf/2609.33926v2'],'version':'arXiv v2, 2026-09-29'},
 {'id':'M05','title':'A realistic MAP/PH/c queuing model for electric vehicle charging stations: theoretical development and real-world case study','filename':'M05_MAP-PH-c-EV-charging_TransportmetricaB2026.pdf','urls':['https://www.tandfonline.com/doi/pdf/10.1080/21680566.2026.2642261'],'version':'Published article'}
]
def fetch(p):
    p=dict(p); p['attempts']=[]
    dest=ROOT/p['filename']
    if dest.exists():
        b=dest.read_bytes(); reader=PdfReader(BytesIO(b)); p.update(status='downloaded',pages=len(reader.pages),bytes=len(b),path=str(dest)); return p
    for url in p['urls']:
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/pdf,*/*;q=0.8'})
            with urlopen(req,timeout=25) as r:
                b=r.read(40_000_000); final_url=r.geturl(); ctype=r.headers.get('Content-Type','')
            if not b.startswith(b'%PDF-'):
                p['attempts'].append({'url':url,'error':'not a PDF','content_type':ctype,'bytes':len(b)}); continue
            reader=PdfReader(BytesIO(b)); pages=len(reader.pages)
            title_text=(reader.pages[0].extract_text() or '')[:500]
            dest.write_bytes(b)
            p.update(status='downloaded',pages=pages,bytes=len(b),path=str(dest),source_url=url,final_url=final_url,sha256=hashlib.sha256(b).hexdigest(),first_page_preview=title_text)
            return p
        except Exception as e:
            p['attempts'].append({'url':url,'error':str(e)[:350]})
    p['status']='unavailable'; return p
results=[]
with ThreadPoolExecutor(max_workers=5) as pool:
    for f in as_completed([pool.submit(fetch,p) for p in PAPERS]):
        r=f.result(); results.append(r)
        print(json.dumps(r,ensure_ascii=False),flush=True)
results.sort(key=lambda x:x['id'])
(ROOT/'download_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
