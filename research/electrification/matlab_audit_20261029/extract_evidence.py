"""Read the frozen DOCX; write evidence only with an explicit --out directory."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


def tag(node):
    return node.tag.rsplit('}', 1)[-1]


def text(node):
    name = tag(node)
    if name in ('t', 'delText'):
        return node.text or ''
    if name.endswith('Pr'):
        return ''
    if name in ('tab', 'br', 'cr'):
        return ' '
    if name == 'f':
        num = ''.join(text(c) for c in node if tag(c) == 'num')
        den = ''.join(text(c) for c in node if tag(c) == 'den')
        return '\\frac{' + num + '}{' + den + '}'
    if name in ('sSub', 'sSup', 'sSubSup'):
        vals = {k: ''.join(text(c) for c in node if tag(c) == k)
                for k in ('e', 'sub', 'sup')}
        return (vals['e'] + ('_{' + vals['sub'] + '}' if vals['sub'] else '')
                + ('^{' + vals['sup'] + '}' if vals['sup'] else ''))
    value = ''.join(text(c) for c in node)
    return '$' + value + '$' if name == 'oMath' else value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[3]
    manuscript = root / 'main_paper/Electrification tipping point_manuscript 202603submit.docx'
    with ZipFile(manuscript) as archive:
        doc = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    ps = doc.findall('.//w:body//w:p', ns)
    records = [{'paragraph': i + 1, 'text': text(p)}
               for i, p in enumerate(ps) if text(p).strip()]
    history = json.loads((root / 'research/electrification/manuscript_extracted.json').read_text('utf-8'))
    result = {
        'source': str(manuscript),
        'sha256': hashlib.sha256(manuscript.read_bytes()).hexdigest(),
        'scope': 'Content and OMML only; paragraph IDs are XML order, not page numbers.',
        'matches_historical_extraction': records == history,
        'records': records,
    }
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'manuscript_evidence.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
