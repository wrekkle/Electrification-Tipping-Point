
import hashlib, os
from docx import Document
def sha(p):
    h = hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda: f.read(1<<20), b''): h.update(c)
    return h.hexdigest()
files = (('rev3', r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx'),
         ('si', r'paper\draft\Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx'),
         ('rev2', r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx'),
         ('rev1', r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx'),
         ('frozen', r'main_paper\Electrification tipping point_manuscript 202603submit.docx'),
         ('pdf', r'research\round6_20261031\c_paper\round6_rev3_draft.pdf'),
         ('sipdf', r'research\round6_20261031\c_paper\round6_rev2_supplement.pdf'))
for k,p in files:
    print(k, sha(p), os.path.getmtime(p), os.path.getsize(p))
d = Document(r'paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx')
text = chr(10).join(p.text for p in d.paragraphs)
for t in ('global optimum', 'invaluable', 'profound insights', 'best evaluated point within that grid',
          'does not certify optimality outside the grid', 'Enumeration certifies optimality over the enumerated grid only',
          'under the submitted cost model', 'not a claim that the configuration is socially optimal',
          'count-difference coupling', 'dominance coupling'):
    print('CHECK', repr(t), text.count(t))
s = Document(r'paper\draft\Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx')
st = chr(10).join(p.text for p in s.paragraphs)
for t in ('count difference a-b', 'does not use any smallest-index', '26,000', 'capacity-difference', 'dominance coupling', 'mirror coupling'):
    print('SI', repr(t), st.count(t))
print('SI has A5 independent of bay order:', 'which free bay is chosen does not affect admission' in st)
