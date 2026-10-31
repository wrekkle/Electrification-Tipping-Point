# -*- coding: utf-8 -*-
import json,csv,sys,statistics
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT='research/round8_20261031'; OUT=ROOT+'/analysis'
def rc(p):
    f=open(p,encoding='utf-8'); rs=list(csv.DictReader(f)); f.close(); return rs
c=json.load(open(ROOT+'/data/processed/public_parking_events.json',encoding='utf-8'))
ev=c['events']; sites=c['sites']
# (a) demand-dwell matching: ideal session failure and energy rate by declared energy level
rows=[]
for E0 in (2.0,4.0,6.0,8.0,10.0,14.0,20.0):
    n=0; dem=0.0; dlv=0.0; fail=0
    for e in ev:
        if not (e.get('is_ev') and e.get('needs_charge')): continue
        T=float(e['dwell_min'])/60.0; E=E0; cap=22.0*T
        n+=1; dem+=E; dlv+=min(E,cap); fail+= 1 if E>cap+1e-9 else 0
    rows.append({'declared_energy_kwh':E0,'n_requests':n,'demand_kwh':round(dem,1),'ideal_delivered_kwh':round(dlv,1),
                 'ideal_energy_rate':round(dlv/dem,4),'session_failure':fail,'session_failure_rate':round(fail/n,4),
                 'meets_5pct_session_standard': (fail/n)<=0.05})
with open(OUT+'/demand_dwell_matching.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
for r in rows: print('E=%s kWh -> ideal rate %.3f, session failure %.3f, meets5%%=%s'%(r['declared_energy_kwh'],r['ideal_energy_rate'],r['session_failure_rate'],r['meets_5pct_session_standard']))
# per-site: dwell needed for 14 kWh at 22 kW vs observed dwell distribution
req_min=14.0/22.0*60
print('14 kWh at 22 kW needs %.1f min'%req_min)
pw=[]
for s in sites:
    dw=sorted(float(e['dwell_min']) for e in ev if e['site_id']==s['site_id'] and e.get('is_ev') and e.get('needs_charge'))
    if not dw: continue
    share=sum(1 for d in dw if d<req_min)/len(dw)
    pw.append({'site_id':s['site_id'],'n_charge_requests':len(dw),'dwell_median_min':round(statistics.median(dw),2),
               'dwell_p90_min':round(dw[int(len(dw)*0.9)],2),'share_dwell_below_required':round(share,4),'required_min_14kwh_22kw':round(req_min,1)})
with open(OUT+'/dwell_vs_required.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(pw[0].keys())); w.writeheader(); w.writerows(pw)
for r in pw: print(r['site_id'],'n',r['n_charge_requests'],'dwell_med',r['dwell_median_min'],'share_below_req',r['share_dwell_below_required'])
# (b) area selection: why 10 of 24
ar=rc(OUT+'/area_ranking.csv'); sel={s['site_id'] for s in sites}
print('--- area ranking 24 areas (area, events, bays, complete_days, selected) ---')
for r in ar: print(r['area'],r['events'],r['bays'],r['complete_days'],r['dwell_median'],'SEL' if r['area'] in sel else '-')
# (c) event share by site
tot=len(ev); print('--- charge demand share ---')
for s in sites:
    es=[e for e in ev if e['site_id']==s['site_id']]
    n=len(es); cr=sum(1 for e in es if e.get('is_ev') and e.get('needs_charge'))
    print(s['site_id'],'events',n,'EV',sum(1 for e in es if e.get('is_ev')),'charge_req',cr,'%.1f%%'%(100*cr/n))