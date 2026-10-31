
import csv, json, sys, os, collections, hashlib, math, glob
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.abspath('.')
E = os.path.join(ROOT, 'research', 'round8_20261031', 'experiments')
sys.path.insert(0, os.path.join(ROOT, 'apps', 'parking_lab'))
sys.path.insert(0, os.path.join(ROOT, 'research', 'round8_20261031', 'engine'))
from workbench import publicdata as pd
from workbench import stat_tools
import runner, offline_opt

def R(f): return list(csv.DictReader(open(os.path.join(E, f), encoding='utf-8')))
def J(f): return json.load(open(os.path.join(E, f), encoding='utf-8'))
rm = J('run_meta.json')
print('E3_CONSTRUCTION', json.dumps(rm.get('e3_instance_construction'), ensure_ascii=False)[:1200])
print('M3_PAIRS', json.dumps(rm.get('m3_pairs'), ensure_ascii=False)[:1500])
print('COMPARISONS_KEYS', [c.get('comparison') for c in rm.get('comparisons', [])])

payload = json.load(open(os.path.join(ROOT, 'research', 'round8_20261031', 'data', 'processed', 'public_parking_events.json'), encoding='utf-8'))
norm = pd.normalise_contract(payload)
blocks = pd.site_day_blocks(norm)
split = pd.split_site_days(blocks, seed=20261031)
tsite = set(split['test_site_ids']); tday = set(split['test_day_keys'])

# ---------- E4 ----------
e4 = R('E4/test_E4.csv')
print('\nE4 rows', len(e4), 'streams', len(set(r['stream_id'] for r in e4)), 'policies', sorted(set(r['policy'] for r in e4)))
print('E4 k', collections.Counter(r['k'] for r in e4), 'k_source', collections.Counter(r['k_source'] for r in e4))
print('E4 split labels', collections.Counter(r['split'] for r in e4), 'model', collections.Counter(r['model'] for r in e4).most_common(2))
print('E4 information', collections.Counter(r['information'] for r in e4))
streams = sorted(set(r['stream_id'] for r in e4))
in_test = all((r['site_id'] in tsite or r['day_key'] in tday) for r in e4)
print('E4 all_streams_heldout', in_test)
# paired hashes
by = collections.defaultdict(dict)
for r in e4: by[(r['stream_id'], r['k'])][r['policy']] = r
paired_ok = all(len(p) == 7 for p in by.values())
len_ok = len(by) == 20
print('E4 groups', len(by), 'complete_7_policies', paired_ok)
# B1 vs B2
diffpairs = []
for key, pol in by.items():
    a, b = pol['B1_QUOTA'], pol['B2_LITERATURE']
    cols = ['parking_service_rate','energy_service_rate_incl_rejected','delivered_kwh','demand_kwh','rejected','admitted','service_capacity_unmet_rate','charging_access_rate']
    diffs = {c: (a.get(c), b.get(c)) for c in cols if a.get(c) != b.get(c)}
    if diffs: diffpairs.append((key, diffs))
print('E4 B1/B2 identical_groups', len(by)-len(diffpairs), 'diff_groups', len(diffpairs), 'sample', json.dumps(diffpairs[:3], ensure_ascii=False)[:1200])
# B0 vs B1/B2 distinct?
same_b0 = 0
for key, pol in by.items():
    if pol['B0_FCFS'].get('energy_service_rate_incl_rejected') == pol['B1_QUOTA'].get('energy_service_rate_incl_rejected') and pol['B0_FCFS'].get('parking_service_rate') == pol['B1_QUOTA'].get('parking_service_rate'):
        same_b0 += 1
print('E4 B0==B1 groups', same_b0, '/', len(by))
# energy identities
bad = collections.Counter(); rows_check = 0
for r in e4:
    def f(x):
        return float(x) if x not in ('', None) else None
    d, g = f(r['delivered_kwh']), f(r['gap_kwh']); dem = f(r['demand_kwh'])
    di, gi = f(r['delivered_kwh_incl_rejected']), f(r['gap_kwh_incl_rejected']); demi = f(r['demand_kwh_incl_rejected'])
    if None not in (d, g, dem):
        rows_check += 1
        if abs((d + g) - dem) > 1e-6: bad['delivered+gap!=demand'] += 1
    if None not in (di, gi, demi) and abs((di + gi) - demi) > 1e-6: bad['incl identity'] += 1
    if None not in (dem, demi) and demi + 1e-9 < dem: bad['incl<plain'] += 1
    if dem:
        rate = f(r['energy_service_rate']); 
        if rate is not None and abs(rate - d/dem) > 1e-9: bad['rate formula'] += 1
    if demi:
        rate = f(r['energy_service_rate_incl_rejected'])
        if rate is not None and abs(rate - di/demi) > 1e-9: bad['incl rate formula'] += 1
    rej = int(float(r['rejected'])); 
    if rej > 0 and abs((demi or 0) - (dem or 0)) < 1e-12: bad['rejected_but_no_extra_demand'] += 1
print('E4 energy_identity_checks', rows_check, 'violations', dict(bad))
rejrows = [r for r in e4 if int(float(r['rejected'])) > 0]
print('E4 rejected_rows', len(rejrows), 'by_policy', collections.Counter(r['policy'] for r in rejrows), 'sample', json.dumps({k: rejrows[0][k] for k in ['policy','rejected','delivered_kwh','demand_kwh','delivered_kwh_incl_rejected','demand_kwh_incl_rejected','energy_cat_rejected']}, ensure_ascii=False) if rejrows else None)

# ---------- M2 recompute ----------
ms = J('M/m_summaries.json')
def boot_ci(vals): return stat_tools.bootstrap_ci(vals, n_boot=1000, alpha=0.05, seed=20261031)
for comp in ms['comparisons']:
    if comp['comparison'] != 'M2': continue
    base = comp['pair'].split(' vs ')[1]
    # order: appearance order of streams in csv
    seen = []
    for r in e4:
        if r['stream_id'] not in seen: seen.append(r['stream_id'])
    diffs = []
    for sid in seen:
        a = by[(sid, '1')]['A']; b = by[(sid, '1')][base]
        diffs.append(float(a['energy_service_rate_incl_rejected']) - float(b['energy_service_rate_incl_rejected']))
    ci = boot_ci(diffs)
    print('M2_RECOMPUTE', comp['pair'], 'n=%d' % ci['n_boot'], 'point=%.15f/%.15f low=%.15f/%.15f high=%.15f/%.15f' % (ci['point'], comp['point'], ci['low'], comp['low'], ci['high'], comp['high']))

# ---------- E6 ----------
e6 = R('E6/energy_E6.csv')
print('\nE6 rows', len(e6), 'streams', len(set(r['stream_id'] for r in e6)), 'grid', collections.Counter((r['connector_kw'], r['feeder_kw']) for r in e6))
print('E6 status', collections.Counter((r['offline_status'], r['offline_reason']) for r in e6))
print('E6 status_cols', [c for c in e6[0] if 'offline' in c or 'feasible' in c])
# independent window check from contract events
def event_lookup(site, day):
    return [e for e in norm['events'] if e['site_id'] == site and e['day_key'] == day and e.get('needs_charge')]
for sid in sorted(set(r['stream_id'] for r in e6)):
    rows = [r for r in e6 if r['stream_id'] == sid]
    site, day = rows[0]['site_id'], rows[0]['day_key']
    jobs = event_lookup(site, day)
    viol = {}
    for kw in (7.0, 11.0):
        n = 0
        for e in jobs:
            need = e.get('energy_kwh')
            if need is None: continue
            req = need / kw * 60.0
            win = e.get('dwell_min')
            if win is not None and req > win + 1e-9: n += 1
        viol[kw] = (n, len(jobs))
    print('E6_WINDOW', sid, 'charge_jobs', len(jobs), 'violations_7kW', viol[7.0], 'violations_11kW', viol[11.0],
          'offline', [(r['connector_kw'], r['feeder_kw'], r['offline_status'], r['offline_reason']) for r in rows])

# ---------- statistics ----------
print('\nSTATS:')
for fam, f in [('E2','E2/curve_E2.csv'),('E4','E4/test_E4.csv'),('E5','E5/info_E5.csv'),('E6','E6/energy_E6.csv')]:
    rows = R(f) if os.path.exists(os.path.join(E,f)) else []
    print(' ', fam, 'rows', len(rows), 'streams', len(set(r.get('stream_id') for r in rows)), 'dup(stream,policy,k)', len(rows)-len(set((r.get('stream_id'),r.get('policy'),r.get('k')) for r in rows)))
e5 = R('E5/info_E5.csv')
print(' E5 k_min_feasible values', collections.Counter(r.get('k_min_feasible') for r in e5), 'policies', collections.Counter(r.get('policy') for r in e5))
print(' E5 n_pairs rows', len(e5), 'streams', len(set(r['stream_id'] for r in e5)))

# ---------- main22 ----------
M22 = os.path.join(ROOT, 'research', 'round8_20261031', 'experiments_main22')
print('\nMAIN22 files', sorted(os.path.relpath(os.path.join(dp,f), M22) for dp,_,fs in os.walk(M22) for f in fs))
if os.path.exists(os.path.join(M22,'E1','manifest.json')):
    m22 = json.load(open(os.path.join(M22,'E1','manifest.json'), encoding='utf-8'))
    print('MAIN22_E1_MANIFEST', json.dumps({k: m22.get(k) for k in ('family','status','mode','generated_utc')}, ensure_ascii=False), 'inputs', [(i.get('path'), (i.get('sha256') or '')[:12]) for i in m22.get('inputs') or []])
    for f2 in ['E1/coverage.csv','E1/fit_metrics.csv','E1/fit_params.json']:
        p = os.path.join(M22, f2); q = os.path.join(E, f2)
        if os.path.exists(p) and os.path.exists(q):
            print('MAIN22_EQ', f2, open(p,encoding='utf-8').read() == open(q,encoding='utf-8').read())

# ---------- figures / paper evidence ----------
FG = os.path.join(ROOT, 'research', 'round8_20261031', 'figures')
print('\nFIGURES pngs', [os.path.relpath(p, FG) for p in glob.glob(FG + '/**/*.png', recursive=True)])
PP = os.path.join(ROOT, 'research', 'round8_20261031', 'paper')
evm = json.load(open(os.path.join(PP,'evidence_rev5_main.json'), encoding='utf-8'))
print('PAPER_EVIDENCE_MAIN', json.dumps(evm, ensure_ascii=False)[:1500])
evs = json.load(open(os.path.join(PP,'evidence_rev5_si.json'), encoding='utf-8'))
print('PAPER_EVIDENCE_SI', json.dumps(evs, ensure_ascii=False)[:800])
print('PAPER_FILES', sorted(os.listdir(PP)))
print('REPRO_DIRS', [d for d in glob.glob(os.path.join(ROOT,'research','round8_20261031','*')) if os.path.isdir(d)])
