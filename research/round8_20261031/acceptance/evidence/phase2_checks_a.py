
import csv, json, sys, os, collections, hashlib, random, math, statistics
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.abspath('.')
E = os.path.join(ROOT, 'research', 'round8_20261031', 'experiments')
sys.path.insert(0, os.path.join(ROOT, 'apps', 'parking_lab'))
sys.path.insert(0, os.path.join(ROOT, 'research', 'round8_20261031', 'engine'))
from workbench import publicdata as pd
from workbench import stat_tools
import runner

def R(f): return list(csv.DictReader(open(os.path.join(E, f), encoding='utf-8')))
def J(f): return json.load(open(os.path.join(E, f), encoding='utf-8'))
def pct(vals, q):
    import math
    s = sorted(vals); n = len(s)
    if n == 0: return None
    idx = q * (n - 1); lo = int(math.floor(idx)); hi = int(math.ceil(idx))
    if lo == hi: return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)
def ks(a, b):
    sa, sb = sorted(a), sorted(b); na, nb = len(sa), len(sb)
    i = j = 0; best = 0.0
    while i < na or j < nb:
        if j >= nb or (i < na and sa[i] <= sb[j]):
            i += 1
        else:
            j += 1
        if i < na:
            while i < na and sa[i] == sa[i-1]: i += 1
        if j < nb:
            while j < nb and sb[j] == sb[j-1]: j += 1
        best = max(best, abs(i/na - j/nb))
    return best

contract = os.path.join(ROOT, 'research', 'round8_20261031', 'data', 'processed', 'public_parking_events.json')
payload = json.load(open(contract, encoding='utf-8'))
rep = pd.validate_contract(payload)
print('CONTRACT ok=%s sites=%d events=%d' % (rep['ok'], rep['counts']['sites'], rep['counts']['events_accepted']))
norm = pd.normalise_contract(payload)
blocks = pd.site_day_blocks(norm)
print('BLOCKS', len(blocks), 'keys', list(blocks[0].keys()))
split = pd.split_site_days(blocks, seed=20261031)
print('SPLIT keys', list(split.keys()))
cal, test = split['calibration'], split['test']
rm = json.load(open(os.path.join(E, 'run_meta.json'), encoding='utf-8'))
print('SPLIT n', {'blocks': len(blocks), 'calibration': len(cal), 'test': len(test)}, 'run_meta', rm['split']['n'])
tsite = set(rm['split']['test_site_ids']); tday = set(rm['split']['test_day_keys'])
bad = [b for b in test if not (b['site_id'] in tsite or b['day_key'] in tday)]
bad2 = [b for b in cal if (b['site_id'] in tsite or b['day_key'] in tday)]
print('SPLIT_RULE_VIOLATIONS test=%d cal=%d' % (len(bad), len(bad2)))
print('SPLIT_SITES', tsite, 'TEST_DAYS', len(tday))

# ---------- E1 ----------
cov = J('E1/fit_params.json')
print('\nE1_FIT_PARAMS', json.dumps({k: cov.get(k) for k in ('unit','dataset_id','n_sites','n_days','n_site_days','n_events')}, ensure_ascii=False))
print('E1_CRITERIA', json.dumps(cov.get('criteria'), ensure_ascii=False))
print('E1_PARAM_KEYS', list(cov.keys()))
covrows = R('E1/coverage.csv')
sites = {s['site_id']: s for s in payload['sites']}
comp = collections.Counter()
other = collections.Counter()
for b in blocks: comp[b['site_id']] += 1
contract_complete = payload['coverage']['complete_days']
# recompute complete days independently
def is_complete(ts):
    buckets = set(int(t[11:13]) // 2 for t in ts)
    return len(buckets) >= 6
calc_complete = {}
for s in sites:
    days = collections.defaultdict(list)
    for e in payload['events']:
        if e['site_id'] == s: days[e['arrival_ts'][:10]].append(e['arrival_ts'])
    calc_complete[s] = sorted(d for d, ts in days.items() if is_complete(ts))
print('E1_COMPLETE_DAYS total_calc=%d total_contract=%d all_equal=%s' % (
    sum(len(v) for v in calc_complete.values()), payload['coverage'].get('complete_days_total'),
    all(set(calc_complete[s]) == set(contract_complete.get(s, [])) for s in sites)))
print('E1_COVERAGE rowwise', all(int(r['events']) == sum(1 for e in payload['events'] if e['site_id'] == r['site_id']) and int(r['site_days']) == len(set(e['arrival_ts'][:10] for e in payload['events'] if e['site_id'] == r['site_id'])) and int(r['n_spaces']) == sites[r['site_id']]['n_spaces'] and int(r['charging_bays']) == round(0.2*sites[r['site_id']]['n_spaces']) and int(r['connectors']) == int(r['charging_bays']) for r in covrows))
# rebuild event pools by split
def pool(block_list):
    dwell = {'all': [], 'ev': [], 'ice': []}
    arr = []
    for b in block_list:
        evs = sorted(b['events'], key=lambda e: e['arrival_min'])
        prev = None
        for e in evs:
            d = e.get('dwell_min'); cat = 'ev' if e.get('is_ev') else 'ice'
            if d is not None:
                dwell['all'].append(d); dwell[cat].append(d)
            if prev is not None:
                arr.append(e['arrival_min'] - prev)
            prev = e['arrival_min']
    return dwell, arr
dcal, acal = pool(cal); dtest, atest = pool(test)
fm = { (r['row_kind'], r['category']): r for r in R('E1/fit_metrics.csv') }
print('E1_FIT rows', [(k, v['status'], v['n_calibration'], v['n_test']) for k, v in fm.items()])
for cat in ('all','ev','ice'):
    key = ('dwell_fit', cat)
    row = fm[key]
    print('E1_DWELL', cat, 'n_cal=%d/%s n_test=%d/%s ks=%.10f/%s mean_cal=%.6f/%s mean_test=%.6f/%s p50=%.3f/%.3f p90=%.3f/%.3f' % (
        len(dcal[cat]), row['n_calibration'], len(dtest[cat]), row['n_test'],
        ks(dcal[cat], dtest[cat]), row['ks_statistic'],
        statistics.mean(dcal[cat]), row['mean_calibration'], statistics.mean(dtest[cat]), row['mean_test'],
        pct(dcal[cat], .5), float(row['p50_calibration']), pct(dcal[cat], .9), float(row['p90_calibration'])))
row = fm[('arrival_fit','')]
print('E1_ARRIVAL n_cal=%d/%s n_test=%d/%s ks=%.10f/%s mean_gap_cal=%.7f/%s mean_gap_test=%.7f/%s' % (
    len(acal), row['n_calibration'], len(atest), row['n_test'], ks(acal, atest), row['ks_statistic'],
    statistics.mean(acal), row['mean_gap_calibration'], statistics.mean(atest), row['mean_gap_test']))

# ---------- E2 ----------
e2 = R('E2/curve_E2.csv'); e2s = R('E2/curve_E2_summary.csv')
groups = collections.OrderedDict()
for r in e2:
    if r.get('status') == 'error': continue
    groups.setdefault((r['policy'], int(r['k'])), []).append(r)
METRICS = ("service_capacity_unmet_rate","service_ev_parking_failure_rate","service_ice_parking_failure_rate","charging_access_rate","energy_service_rate")
print('\nE2 summary rows', len(e2s), 'groups', len(groups))
maxdiff = 0.0; ci_bad = 0; mismatch = []
for srow in e2s:
    key = (srow['policy'], int(srow['k'])); sub = groups[key]
    if len(sub) != int(srow['n_streams']): mismatch.append(('n_streams', key, len(sub), srow['n_streams']))
    for m in METRICS:
        vals = [float(x[m]) for x in sub if x.get(m) not in ('', None)]
        if len(vals) < 2: continue
        ci = stat_tools.bootstrap_ci(vals, n_boot=1000, alpha=0.05, seed=20261031)
        for tag, got, exp in (('mean', ci['point'], float(srow[m+'_mean'])), ('low', ci['low'], float(srow[m+'_low'])), ('high', ci['high'], float(srow[m+'_high']))):
            d = abs(got-exp); maxdiff = max(maxdiff, d)
            if d > 1e-9: mismatch.append((key, m, tag, got, exp))
print('E2_BOOTSTRAP_RECOMPUTE max_abs_diff=%.3e mismatches=%d' % (maxdiff, len(mismatch)))
print('E2_MISMATCH_SAMPLE', mismatch[:3])
sizes = [(k, len(v)) for k, v in groups.items() if k[0] == 'A']
print('E2_STREAMS_PER_K', sizes)
print('E2_DUP_ROWS', len(e2) - len(set((r['stream_id'], r['policy'], r['k']) for r in e2)))
print('E2_POLICIES', sorted(set(r['policy'] for r in e2)), 'STREAMS', len(set(r['stream_id'] for r in e2)), 'HASH_UNIQUE', len(set(r['stream_hash'] for r in e2)))
print('E2_SUMMARY_META', open(os.path.join(E,'E2','curve_E2_summary.json'), encoding='utf-8').read()[:600])

# ---------- E3 ----------
cls = J('E3/classes.json'); search = R('E3/search_E3.csv')
per = collections.defaultdict(dict)
for r in search:
    if r.get('row_kind') == 'per_k':
        per[r['instance_id']][int(r['k'])] = r
print('\nE3 classes', cls['classes'], 'instances', len(cls['instances']), 'searchrows', len(search), 'per_k rows', sum(len(v) for v in per.values()))
for inst in cls['instances']:
    iid = inst['instance_id']; ks = sorted(per.get(iid, {}).keys()); physical = int(inst['physical_bound'])
    statuses = {k: per[iid][k]['status'] for k in ks}
    allinf = all(s == 'infeasible' for s in statuses.values())
    contiguous = ks == list(range(0, max(ks)+1)) if ks else False
    ok_class = False
    if inst['class'] == 'physically_infeasible':
        ok_class = allinf and max(ks) == physical and inst['stop_reason'] == 'exhausted_physical_bound'
    elif inst['class'] == 'budget_not_covered':
        ok_class = allinf and max(ks) < physical and inst['stop_reason'] == 'budget_cap'
    elif inst['class'] == 'confirmed_minimal':
        ok_class = inst['k_star'] is not None and all(statuses[k]=='infeasible' for k in ks if k < inst['k_star'])
    print('E3_INST', iid, inst['class'], 'k=[%d..%d]' % (min(ks), max(ks)), 'physical', physical, 'allinf', allinf, 'contiguous', contiguous, 'class_ok', ok_class, 'stop', inst['stop_reason'])
print('E3_CONFIRMED_MINIMAL_CLAIMS', sum(1 for i in cls['instances'] if i['class'] == 'confirmed_minimal'), 'k_star_nonnull', sum(1 for i in cls['instances'] if i['k_star'] is not None))
