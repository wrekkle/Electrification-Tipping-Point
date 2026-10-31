import argparse
import concurrent.futures
import hashlib
import io
import json
import logging
import re
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

logging.getLogger('pypdf').setLevel(logging.ERROR)
ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / 'PDFs'
PDF_DIR.mkdir(exist_ok=True)
LOCK = threading.Lock()
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; AcademicPaperDownload/1.0)', 'Accept': 'application/pdf,text/html;q=0.8,*/*;q=0.5'}
MAX_BYTES = 35 * 1024 * 1024

CANDIDATES = {
 'P01': ['https://calhoun.nps.edu/server/api/core/bitstreams/45ac1cd2-5bd3-41df-82b4-9902c1dda86e/content'],
 'P02': ['https://www.dcscience.net/Hawkes-Biometrika-1971.pdf'],
 'P03': ['https://hanjun-dai.github.io/pdf/DuDaiTriUpa2016.pdf'],
 'P04': ['https://arxiv.org/pdf/1612.09328'],
 'P05': ['https://www.sciencedirect.com/science/article/pii/S0305048316000165/pdfft'],
 'P06': ['https://www.sciencedirect.com/science/article/pii/S235214652300323X/pdf'],
 'P07': ['https://projecteuclid.org/journals/annals-of-applied-probability/volume-1/issue-3/Loss-Networks/10.1214/aoap/1177005872.pdf', 'https://www.statslab.cam.ac.uk/~fpk1/PAPERS/loss.html'],
 'P08': ['https://www.tandfonline.com/doi/pdf/10.1081/STM-120001221'],
 'P09': ['https://research.tilburguniversity.edu/files/76625029/1-s2.0-S0377221723005404-main.pdf', 'https://pure.uvt.nl/ws/portalfiles/portal/76625029/1-s2.0-S0377221723005404-main.pdf'],
 'P10': ['https://arxiv.org/pdf/2002.02430'],
 'P11': ['https://papers.ssrn.com/sol3/Delivery.cfm/4320423.pdf?abstractid=4320423'],
 'P12': ['https://papers.ssrn.com/sol3/Delivery.cfm/6384158.pdf?abstractid=6384158'],
 'P13': ['https://papers.ssrn.com/sol3/Delivery.cfm/7109699.pdf?abstractid=7109699'],
 'P14': ['https://openreview.net/pdf/36c527b4deca3b50b6d26eea316e65919aa99329.pdf'],
 'P15': ['https://arxiv.org/pdf/1901.05028', 'https://par.nsf.gov/servlets/purl/10240305'],
 'P16': ['https://arxiv.org/pdf/2509.02302v2'],
 'P17': ['https://arxiv.org/pdf/1402.5481'],
 'P18': ['https://par.nsf.gov/servlets/purl/10339524', 'https://arxiv.org/pdf/1710.08005'],
 'P19': ['https://arxiv.org/pdf/1505.05116', 'https://link.springer.com/content/pdf/10.1007/s10107-017-1172-1.pdf'],
 'P20': ['https://web.stanford.edu/~yyye/distRobOpt_OR_rev0.pdf'],
 'P21': ['https://pubsonline.informs.org/doi/pdf/10.1287/opre.1050.0216'],
 'P22': ['https://sites.math.washington.edu/~rtr/papers/rtr179-CVaR1.pdf'],
 'P23': ['https://arxiv.org/pdf/2106.00170'],
 'P24': ['https://arxiv.org/pdf/2202.13415'],
 'P25': ['https://escholarship.org/content/qt1wt3d4vr/qt1wt3d4vr.pdf', 'https://escholarship.org/uc/item/1wt3d4vr'],
 'P26': ['https://nathanieltucker.github.io/2019_TSG_pre_full.pdf', 'https://arxiv.org/pdf/1905.06468'],
 'P27': ['https://strathprints.strath.ac.uk/73587/1/Safak_Bayram_etal_JES_2020_A_probabilistic_capacity_planning_methodology_for_plug_in_electric_vehicle.pdf'],
 'P28': ['https://www.sciencedirect.com/science/article/pii/S136655452500479X/pdf'],
 'P29': ['https://papers.ssrn.com/sol3/Delivery.cfm/6254138.pdf?abstractid=6254138'],
 'P30': ['https://ntnuopen.ntnu.no/ntnu-xmlui/bitstream/handle/11250/3181000/1-s2.0-S2095756423001253-main.pdf?sequence=1'],
 'P31': ['https://journals.sagepub.com/doi/pdf/10.1177/03611981251405254'],
 'P32': ['https://ev.caltech.edu/assets/pub/ACN_Data_Analysis_and_Applications.pdf', 'https://par.nsf.gov/servlets/purl/10200593'],
 'P33': ['https://arxiv.org/pdf/2012.02809'],
 'P34': ['https://pubsonline.informs.org/doi/pdf/10.1287/moor.2023.0250'],
 'P35': ['https://pubsonline.informs.org/doi/pdf/10.1287/opre.2022.0604'],
}

def norm(text):
    text = unicodedata.normalize('NFKD', text)
    return re.sub(r'[^a-z0-9 ]', ' ', text.lower())

def inspect_pdf(data, paper):
    if b'%PDF-' not in data[:1024]:
        raise ValueError('response is not PDF')
    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted and reader.decrypt('') == 0:
        raise ValueError('encrypted PDF')
    pages = len(reader.pages)
    if pages < 2:
        raise ValueError('fewer than 2 pages; likely abstract/cover')
    first_text = '\n'.join((reader.pages[i].extract_text() or '') for i in range(min(3, pages)))
    text_words = set(norm(first_text).split())
    ignore = {'the','of','for','a','an','and','in','with','to','on','by','under','using','from','then','at','as'}
    title_words = set(norm(paper['title']).split()) - ignore
    coverage = len(title_words & text_words) / max(1, len(title_words))
    if len(text_words) > 20 and coverage < 0.55:
        raise ValueError(f'title mismatch (keyword coverage {coverage:.2f})')
    return {'pages': pages, 'title_keyword_coverage': round(coverage, 3), 'text_verified': len(text_words)>20,
            'first_text_excerpt': first_text[:850], 'sha256': hashlib.sha256(data).hexdigest()}

def html_pdf_links(body, base):
    links = []
    patterns = [
        r'<meta[^>]+name=[\"\']citation_pdf_url[\"\'][^>]+content=[\"\']([^\"\']+)',
        r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+name=[\"\']citation_pdf_url[\"\']',
    ]
    for pattern in patterns:
        links.extend(urljoin(base, x.replace('&amp;', '&')) for x in re.findall(pattern, body, re.I))
    return list(dict.fromkeys(links))[:3]

def fetch_url(url, paper, depth=0):
    with urlopen(Request(url, headers=HEADERS), timeout=30) as response:
        data = bytearray()
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise ValueError('download exceeds 35 MB')
        data = bytes(data)
        if b'%PDF-' in data[:1024]:
            meta = inspect_pdf(data, paper)
            return data, response.geturl(), meta
        if depth == 0:
            for link in html_pdf_links(data.decode(response.headers.get_content_charset() or 'utf-8', errors='replace'), response.geturl()):
                try:
                    return fetch_url(link, paper, depth=1)
                except Exception:
                    pass
        raise ValueError(f'HTML or other non-PDF response ({response.headers.get("Content-Type", "unknown")})')

def filename(paper):
    slug = re.sub(r'[^A-Za-z0-9]+', '_', unicodedata.normalize('NFKD', paper['title'])).strip('_')[:145]
    return f"{paper['id']}_{slug}.pdf"

def download_one(paper):
    target = PDF_DIR / filename(paper)
    if target.exists():
        try:
            meta = inspect_pdf(target.read_bytes(), paper)
            return dict(id=paper['id'], status='downloaded', filename=target.name, existing=True, **meta)
        except Exception:
            pass
    attempts = []
    urls = CANDIDATES.get(paper['id'], [])
    extra = ROOT / 'extra_download_sources.json'
    if extra.exists():
        urls = json.loads(extra.read_text(encoding='utf-8')).get(paper['id'], []) + urls
    for url in dict.fromkeys(urls):
        try:
            data, resolved, meta = fetch_url(url, paper)
            target.write_bytes(data)
            return dict(id=paper['id'], status='downloaded', filename=target.name, source_url=url,
                        resolved_url=resolved, bytes=len(data), attempts=attempts, **meta)
        except Exception as exc:
            attempts.append({'url': url, 'error': str(exc)[:260]})
    return dict(id=paper['id'], status='not_downloaded', attempts=attempts)

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ids', nargs='*')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    papers = json.loads((ROOT/'sources.json').read_text(encoding='utf-8'))
    old_path = ROOT/'download_status.json'
    records = json.loads(old_path.read_text(encoding='utf-8')) if old_path.exists() else {}
    selected = [p for p in papers if not args.ids or p['id'] in args.ids]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(download_one, p):p for p in selected}
        for future in concurrent.futures.as_completed(pending):
            paper = pending[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {'id':paper['id'], 'status':'not_downloaded', 'attempts':[{'error':str(exc)}]}
            if record.get('existing') and paper['id'] in records:
                record = dict(records[paper['id']], **{k:v for k,v in record.items() if k!='attempts'})
            records[paper['id']] = record
            old_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({k:record.get(k) for k in ['id','status','pages','filename']},ensure_ascii=True),flush=True)
    count = sum(r.get('status')=='downloaded' for r in records.values())
    print(json.dumps({'downloaded':count,'total':len(papers),'missing':[p['id'] for p in papers if records.get(p['id'],{}).get('status')!='downloaded']},ensure_ascii=True),flush=True)

if __name__ == '__main__':
    run()
