
import os, hashlib
from docx import Document
ROOT = r'C:\Projects\停车场充电桩优化方案'
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1<<20), b''): h.update(c)
    return h.hexdigest()
files = {
 'rev2': r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx',
 'si': r'paper\draft\Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx',
 'rev1': r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx',
 'frozen': r'main_paper\Electrification tipping point_manuscript 202603submit.docx',
 'base': r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx',
 'pdf': r'research\round6_20261031\c_paper\round6_rev2_draft.pdf',
 'sipdf': r'research\round6_20261031\c_paper\round6_rev2_supplement.pdf',
}
for k, p in files.items():
    fp = os.path.join(ROOT, p)
    print(k, sha(fp), os.path.getmtime(fp), os.path.getsize(fp))
d = Document(os.path.join(ROOT, files['rev2']))
text = '\n'.join(p.text for p in d.paragraphs)
for b in ['mirror coupling', 'second experiment', 'could be worth', 'restores admissibility in 4',
          'the first rule is the dedicated rule', 'placeholder', 'to be produced', 'To be drawn',
          'to be reassigned', 'shared rule restores', 'shared rule lowers', 'dominance coupling',
          'value of information', 'within the enumerated range 0-40']:
    print('SCAN', repr(b), '->', text.count(b))
print('SUP pointer count', text.count('Supplementary Note'))
s = Document(os.path.join(ROOT, files['si']))
st = '\n'.join(p.text for p in s.paragraphs)
for b in ['placeholder', 'to be produced', 'TBD', 'mirror coupling']:
    print('SISCAN', repr(b), '->', st.count(b))
print('SI paras', len(s.paragraphs), 'tables', len(s.tables))
