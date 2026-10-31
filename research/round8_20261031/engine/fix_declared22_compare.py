import csv, json
from pathlib import Path
ROOT = Path(r'C:\Projects\停车场充电桩优化方案')
OUT = ROOT / 'research' / 'round8_20261031' / 'experiments_declared22'

def rows(p):
    with open(p, encoding='utf-8') as fh:
        return list(csv.DictReader(fh))

def num(row, key):
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0

def aggregate_e4(path):
    rs = [r for r in rows(path) if r.get('policy') == 'A']
    delivered = sum(num(r, 'delivered_kwh_incl_rejected') for r in rs)
    demand = sum(num(r, 'demand_kwh_incl_rejected') for r in rs)
    an = sum(num(r, 'charging_access_num') for r in rs)
    ad = sum(num(r, 'charging_access_den') for r in rs)
    return {'n_streams': len(rs),
            'charge_requests': int(sum(num(r, 'den_exogenous_charge_requests') for r in rs)),
            'rejected_visits_all_types': int(sum(num(r, 'rejected') for r in rs)),
            'access_num': int(an), 'access_den': int(ad),
            'access_rate': round(an / ad, 4) if ad else None,
            'delivered_kwh': round(delivered, 1), 'demand_kwh': round(demand, 1),
            'gap_kwh': round(demand - delivered, 1),
            'energy_service_rate': round(delivered / demand, 4) if demand else None,
            'k': sorted({r['k'] for r in rs})}

comparison = []
comparison.append({'run': '7kW_experiments', **aggregate_e4(ROOT / 'research/round8_20261031/experiments/E4/test_E4.csv'),
                   'hardware_note': '审计后确认：resolved=契约声明 20%，无 4-connector 上限（见 hardware_audit.json）'})
comparison.append({'run': 'main22_experiments', **aggregate_e4(ROOT / 'research/round8_20261031/experiments_main22/E4/test_E4.csv'),
                   'hardware_note': '22 kW, feeder=k*22；charging_bays/connectors 来自契约声明'})
def aggregate_rows(rs):
    delivered = sum(num(r, 'delivered_kwh_incl_rejected') for r in rs)
    demand = sum(num(r, 'demand_kwh_incl_rejected') for r in rs)
    an = sum(num(r, 'charging_access_num') for r in rs)
    ad = sum(num(r, 'charging_access_den') for r in rs)
    return {'n_streams': len(rs),
            'charge_requests': int(sum(num(r, 'den_exogenous_charge_requests') for r in rs)),
            'rejected_visits_all_types': int(sum(num(r, 'rejected') for r in rs)),
            'access_num': int(an), 'access_den': int(ad),
            'access_rate': round(an / ad, 4) if ad else None,
            'delivered_kwh': round(delivered, 1), 'demand_kwh': round(demand, 1),
            'gap_kwh': round(demand - delivered, 1),
            'energy_service_rate': round(delivered / demand, 4) if demand else None}

decl = [r for r in rows(OUT / 'E4/test_E4.csv')
        if r.get('policy') == 'A' and r.get('k_source', '').startswith('preregistered')]
comparison.append({'run': 'declared22_k_prereg', 'k': 'prereg(1)',
                   'hardware_note': '契约声明硬件（20%）+22kW；k=1', **aggregate_rows(decl)})
ps = rows(OUT / 'per_stream_declared22.csv')
total = sum(int(r['charge_requests']) for r in ps)
gate = sum(int(r['gate_rejections']) for r in ps)
noconn = sum(int(r['no_connector']) for r in ps)
short = sum(int(r['shortfall_sessions']) for r in ps)
delivered = sum(num(r, 'delivered_kwh') for r in ps)
demand = sum(num(r, 'demand_kwh') for r in ps)
caps = [num(r, 'capacity_only_unmet_at_eval') for r in ps]
comparison.append({'run': 'declared22_at_declared_max_k', 'k': 'declared_max_k (2..16)',
                   'hardware_note': '契约声明硬件（20%）+22kW；k=declared charging_bays',
                   'n_streams': len(ps), 'charge_requests': total,
                   'gate_rejections_charge_requests': gate, 'no_connector': noconn,
                   'access_num': total - gate - noconn, 'access_den': total,
                   'access_rate': round((total - gate - noconn) / total, 4) if total else None,
                   'shortfall_sessions': short,
                   'delivered_kwh': round(delivered, 1), 'demand_kwh': round(demand, 1),
                   'gap_kwh': round(demand - delivered, 1),
                   'energy_service_rate': round(delivered / demand, 4) if demand else None,
                   'capacity_only_unmet_mean': round(sum(caps) / len(caps), 4),
                   'capacity_only_unmet_median': round(sorted(caps)[len(caps) // 2], 4)})
fields = []
for row in comparison:
    for key in row:
        if key not in fields:
            fields.append(key)
with open(OUT / 'comparison_overrides.csv', 'w', encoding='utf-8', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=fields, lineterminator='\n')
    w.writeheader(); w.writerows(comparison)
meta = json.loads((OUT / 'run_meta.json').read_text(encoding='utf-8'))
meta['comparison'] = comparison
meta['comparison_note'] = ('审计结论：7kW/main22 实际使用契约声明硬件（charging_bays 16/12/7/14/8/3/7/3/2/4），'
                          '未应用 charging_bay_share=0.1/max_connectors_per_site=4；'
                          'main22 仅强制 connector_kw=22 与 feeder=connectors*22。')
(OUT / 'run_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
import hashlib
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
targets = ['E3/search_E3.csv', 'E3/classes.json', 'E4/test_E4.csv', 'E4/m2_declared22.json',
           'E6/energy_E6.csv', 'M/m_summaries.csv', 'M/m_summaries.json',
           'per_stream_declared22.csv', 'comparison_overrides.csv', 'hardware_audit.json']
manifest['outputs'] = [{'path': t, 'sha256': sha(OUT / t)} for t in targets]
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'comparison': comparison, 'classes': meta['classes'],
                  'm1_status': meta['m1_status'], 'm3_status': meta['m3_status'],
                  'm2': meta['m2']}, ensure_ascii=True, default=str))
