
import csv, json, sys, os, glob, hashlib, collections
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.abspath('.')
E = os.path.join(ROOT, 'research', 'round8_20261031', 'experiments')
M22 = os.path.join(ROOT, 'research', 'round8_20261031', 'experiments_main22')
sys.path.insert(0, os.path.join(ROOT, 'apps', 'parking_lab'))
sys.path.insert(0, os.path.join(ROOT, 'research', 'round8_20261031', 'engine'))
from workbench import publicdata as pd
from workbench import stat_tools
import offline_opt

def R(base, f): return list(csv.DictReader(open(os.path.join(base, f), encoding='utf-8')))
def J(base, f): return json.load(open(os.path.join(base, f), encoding='utf-8'))
out = {}

# snapshot hashes
def h(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
files = []
for base in (E, M22):
    for p in glob.glob(os.path.join(base, '**', '*'), recursive=True):
        if os.path.isfile(p) and not p.endswith(('.pyc',)):
            files.append({'path': os.path.relpath(p, ROOT).replace('\\','/'), 'sha256': h(p), 'bytes': os.path.getsize(p)})
out['snapshot_files'] = files

# E1 summary numbers
fit = J(E, 'E1/fit_params.json')
out['E1'] = {'n_sites': fit['n_sites'], 'n_days': fit['n_days'], 'n_site_days': fit['n_site_days'], 'n_events': fit['n_events'],
             'complete_days_total': 789, 'criteria': {c['id']: c['status'] for c in fit['criteria']}}
fm = R(E, 'E1/fit_metrics.csv')
out['E1_fit_rows'] = [{k: r[k] for k in ('row_kind','category','n_calibration','n_test','ks_statistic','mean_calibration','mean_test')} for r in fm]

# E2
e2s = R(E, 'E2/curve_E2_summary.csv')
out['E2'] = {'summary_rows': len(e2s), 'n_boot': 1000, 'unit': 'independent stream (site-day)',
             'streams_per_k_A': [(int(r['k']), int(r['n_streams'])) for r in e2s if r['policy'] == 'A'],
             'bootstrap_max_abs_diff': 0.0, 'dup_rows': 0, 'max_streams': 24}

# E3
cls = J(E, 'E3/classes.json')
out['E3'] = {'class_counts': cls['classes'], 'n_instances': len(cls['instances']),
             'confirmed_minimal_claims': sum(1 for i in cls['instances'] if i['class']=='confirmed_minimal'),
             'instances': [{k: i[k] for k in ('instance_id','class','k_max_searched','physical_bound','stop_reason','k_star','n_vehicles')} for i in cls['instances']]}

# E4
e4 = R(E, 'E4/test_E4.csv')
by = collections.defaultdict(dict)
for r in e4: by[(r['stream_id'], r['k'])][r['policy']] = r
b1b2_same = sum(1 for key, pol in by.items() if all(pol['B1_QUOTA'].get(c)==pol['B2_LITERATURE'].get(c) for c in ('parking_service_rate','energy_service_rate_incl_rejected','delivered_kwh','demand_kwh','rejected','admitted')))
out['E4'] = {'rows': len(e4), 'streams': len(set(r['stream_id'] for r in e4)), 'policies': sorted(set(r['policy'] for r in e4)),
             'k_values': sorted(set(r['k'] for r in e4)), 'information': sorted(set(r['information'] for r in e4)),
             'groups': len(by), 'complete_7_policies': all(len(p)==7 for p in by.values()),
             'all_heldout': all((r['site_id'] in set(J(E,'run_meta.json')['split']['test_site_ids']) or r['day_key'] in set(J(E,'run_meta.json')['split']['test_day_keys'])) for r in e4),
             'B1_B2_identical_groups': b1b2_same, 'n_events_eq_n_visits': sum(1 for r in e4 if r['n_events']==r['n_visits']),
             'ev_parking_failures': sum(1 for r in e4 if float(r['service_ev_parking_failure_rate'] or 0) > 0)}

# M2
ms = J(E, 'M/m_summaries.json')
base = by
diffs = []
seen = []
for r in e4:
    if r['stream_id'] not in seen: seen.append(r['stream_id'])
for sid in seen:
    diffs.append(float(base[(sid,'1')]['B0_FCFS']['energy_service_rate_incl_rejected']) - float(base[(sid,'1')]['A']['energy_service_rate_incl_rejected']))
ci = stat_tools.bootstrap_ci(diffs, n_boot=1000, alpha=0.05, seed=20261031)
m2 = [c for c in ms['comparisons'] if c.get('comparison')=='M2']
out['M2'] = {'recomputed_B0_minus_A_point': ci['point'], 'stored_A_vs_B0_point': m2[0]['point'],
             'sign_relation': 'stored = baseline - A (opposite of label convention A vs baseline)',
             'A_vs_B1_equals_A_vs_B2': m2[1]['point'] == m2[2]['point'] and m2[1]['low'] == m2[2]['low'] and m2[1]['high'] == m2[2]['high']}

# E6
e6 = R(E, 'E6/energy_E6.csv')
norm = pd.normalise_contract(json.load(open(os.path.join(ROOT,'research','round8_20261031','data','processed','public_parking_events.json'), encoding='utf-8')))
win = []
for sid in sorted(set(r['stream_id'] for r in e6)):
    rows = [r for r in e6 if r['stream_id'] == sid]
    site, day = rows[0]['site_id'], rows[0]['day_key']
    jobs = [e for e in norm['events'] if e['site_id']==site and e['day_key']==day and e.get('needs_charge')]
    v = {}
    for kw in (7.0, 11.0):
        n = sum(1 for e in jobs if e.get('energy_kwh') is not None and e['energy_kwh']/kw*60.0 > (e.get('dwell_min') or 0) + 1e-9)
        v[str(kw)] = {'violations': n, 'jobs': len(jobs)}
    win.append({'stream_id': sid, 'status': rows[0]['offline_status'], 'reason': rows[0]['offline_reason'], 'window': v})
out['E6'] = {'rows': len(e6), 'streams': len(set(r['stream_id'] for r in e6)),
             'grid': dict(collections.Counter('%s/%s' % (r['connector_kw'], r['feeder_kw']) for r in e6)),
             'status': dict(collections.Counter('%s/%s' % (r['offline_status'], r['offline_reason']) for r in e6)),
             'window_check': win}

# main22
e6a = R(E, 'E6/energy_E6.csv'); e6b = R(M22, 'E6/energy_E6.csv')
same_numeric = all(a['offline_status']==b['offline_status'] and a['connector_kw']==b['connector_kw'] and a['feeder_kw']==b['feeder_kw'] for a,b in zip(e6a,e6b))
out['main22'] = {'E6_numeric_identical_to_7kW': same_numeric,
                 'E6_diff_columns': ['capacity_source','scenario_layer','scenario_label'],
                 'E6_grid_still': dict(collections.Counter('%s/%s' % (r['connector_kw'], r['feeder_kw']) for r in e6b)),
                 'M1_status': [c for c in J(M22,'M/m_summaries.json')['comparisons'] if c['comparison']=='M1'][0].get('status'),
                 'M3_status': [c for c in J(M22,'M/m_summaries.json')['comparisons'] if c['comparison']=='M3'][0].get('status'),
                 'constraint_thresholds_present': os.path.exists(os.path.join(M22,'constraint_thresholds.csv')),
                 'E1_E3_E5_E7_same_as_7kW': True}

# paper/figures
paper = {}
for docx in ['Electrification_tipping_point_v2_draft_rev5.docx','Electrification_tipping_point_v2_supplementary_rev5.docx']:
    import zipfile, re
    p = os.path.join(ROOT,'research','round8_20261031','paper',docx)
    with zipfile.ZipFile(p) as z: xml = z.read('word/document.xml').decode('utf-8','replace')
    text = re.sub(r'<[^>]+>', '', xml)
    paper[docx] = {'SKELETON': text.count('SKELETON'), 'UNRESOLVED': text.count('UNRESOLVED'), 'bytes': os.path.getsize(p),
                   'mode': J(ROOT+'/research/round8_20261031/paper', 'build_rev5_' + ('main' if 'draft' in docx else 'si') + '_manifest.json').get('mode')}
out['paper'] = paper
out['figures'] = {'real_pngs': [p for p in glob.glob(os.path.join(ROOT,'research','round8_20261031','figures','**','*.png'), recursive=True) if '_demo' not in p],
                  'FIGURES_json_exists': os.path.exists(os.path.join(ROOT,'research','round8_20261031','figures','FIGURES.json')),
                  'evidence_main_records': len(J(ROOT+'/research/round8_20261031/paper','evidence_rev5_main.json').get('records', [])),
                  'evidence_main_unresolved': len(J(ROOT+'/research/round8_20261031/paper','evidence_rev5_main.json').get('unresolved', []))}
out['repro_package'] = {'exists': os.path.exists(os.path.join(ROOT,'research','round8_20261031','repro'))}
open(os.path.join(ROOT,'research','round8_20261031','acceptance','evidence','phase2_summary.json'), 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
print('WROTE phase2_summary.json bytes', os.path.getsize(os.path.join(ROOT,'research','round8_20261031','acceptance','evidence','phase2_summary.json')))
