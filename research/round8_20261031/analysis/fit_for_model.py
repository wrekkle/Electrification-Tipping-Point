# -*- coding: utf-8 -*-
import json, csv, sys, math, statistics
from datetime import datetime, timedelta
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT='research/round8_20261031'
CON=ROOT+'/data/processed/public_parking_events.json'
WIN=ROOT+'/data/processed/_window_events.csv'
OUT=ROOT+'/analysis'
import os; os.makedirs(OUT, exist_ok=True)
c=json.load(open(CON,encoding='utf-8'))
sites=c['sites']; ev=c['events']
print('contract events',len(ev),'sites',len(sites))
# ---------- 1. window scope / censoring / initial occupancy ----------
try:
    wf=open(WIN,encoding='utf-8'); wr=csv.DictReader(wf); wrows=list(wr); wf.close()
except Exception as e:
    wrows=[]; print('window read failed',e)
if wrows:
    print('window rows',len(wrows))
    arr=[r['arr_local'] for r in wrows]; dep=[r['dep_local'] for r in wrows if r['dep_local']]
    print('arrival min/max',min(arr),max(arr)); print('departure min/max',min(dep),max(dep))
    areas=Counter(r['area'] for r in wrows); bays=defaultdict(set)
    for r in wrows: bays[r['area']].add(r['bay_id'])
    neg=sum(1 for r in wrows if r['dwell_min'] and float(r['dwell_min'])<0)
    print('distinct areas',len(areas),'negative dwell in window',neg)
    # cross-midnight
    cm=0
    for r in wrows:
        a=r['arr_local']; d=r['dep_local']
        if a and d and a[:10]!=d[:10]: cm+=1
    print('cross-midnight events',cm)
    # initial occupancy: arrival before first window date
    first=min(arr)[:10]; last=max(arr)[:10]
    init=[r for r in wrows if r['arr_local'][:10]<first]
    after=[r for r in wrows if r['dep_local'] and r['dep_local'][:10]>last]
    print('window first/last arrival date',first,last,'initial-occupancy',len(init),'departs-after-window',len(after))
# ---------- 2. area ranking + site audit (capacity, concurrency, dwell) ----------
area_ev=defaultdict(list); area_bays=defaultdict(set); area_streets=defaultdict(set)
by_area=defaultdict(list)
if wrows:
    for r in wrows:
        by_area[r['area']].append(r)
        area_bays[r['area']].add(r['bay_id'])
        area_streets[r['area']].add((r['street'],r['side']))
rank=[]
for a,rows in by_area.items():
    days=defaultdict(set)
    for r in rows:
        days[r['day_local']].add(int(r['arr_local'][11:13])//2)
    complete=sum(1 for d,b in days.items() if len(b)>=6)
    dw=[float(r['dwell_min']) for r in rows if r['dwell_min']]
    rank.append({'area':a,'events':len(rows),'bays':len(area_bays[a]),'block_faces':len(area_streets[a]),
                 'days':len(days),'complete_days':complete,'dwell_median':round(statistics.median(dw),2) if dw else None,
                 'dwell_p90':round(sorted(dw)[int(len(dw)*0.9)],2) if dw else None})
rank.sort(key=lambda x:-x['events'])
with open(OUT+'/area_ranking.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rank[0].keys())); w.writeheader(); w.writerows(rank)
print('areas ranked',len(rank),'| top5',[(r['area'],r['events'],r['bays'],r['complete_days']) for r in rank[:5]])
sel=[s['site_id'] for s in sites]
print('selected sites present in window:',all(s in by_area for s in sel))
# concurrency sweep per site (contract sites only)
site_audit=[]
for s in sites:
    rows=by_area[s['site_id']]; nsp=s['n_spaces']
    pts=[]
    for r in rows:
        a=r['arr_local']; d=r['dep_local']
        if not d: continue
        pts.append((a,1)); pts.append((d,-1))
    pts.sort(key=lambda x:(x[0],-x[1]))
    cur=0; mx=0; over_min=0; last=None
    for t,delta in pts:
        if last is not None and cur>nsp:
            over_min+= 1
        cur+=delta; mx=max(mx,cur); last=t
    # exact overflow duration in minutes
    cur=0; prev=None; over=0.0
    for t,delta in pts:
        if prev is not None:
            dt=(datetime.fromisoformat(t)-datetime.fromisoformat(prev)).total_seconds()/60.0
            if cur>nsp: over+=max(0.0,dt)
        cur+=delta; prev=t
    dw=[float(r['dwell_min']) for r in rows if r['dwell_min']]
    site_audit.append({'site_id':s['site_id'],'n_spaces':nsp,'distinct_bays':len(area_bays[s['site_id']]),
      'block_faces':len(area_streets[s['site_id']]),'events':len(rows),'max_concurrency':mx,'peak_over_capacity':mx-nsp,
      'minutes_above_capacity':round(over,1),'charging_bays':s['charging_bays'],'connectors':s['connectors'],
      'dwell_median_min':round(statistics.median(dw),2) if dw else None,'dwell_p90_min':round(sorted(dw)[int(len(dw)*0.9)],2) if dw else None})
with open(OUT+'/site_audit.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(site_audit[0].keys())); w.writeheader(); w.writerows(site_audit)
print('site audit rows',len(site_audit))
for r in site_audit: print(r['site_id'],'n_spaces',r['n_spaces'],'bays',r['distinct_bays'],'blockfaces',r['block_faces'],'maxconc',r['max_concurrency'],'over',r['peak_over_capacity'],'min_over',r['minutes_above_capacity'],'dwell_med',r['dwell_median_min'])
# ---------- 3. ideal delivery upper bound: min(E, P*T) ----------
def ideal(events, P):
    n=0; dem=0.0; dlv=0.0; fail=0
    for e in events:
        if not (e.get('is_ev') and e.get('needs_charge')): continue
        E=float(e.get('energy_kwh') or 0.0); T=float(e.get('dwell_min') or 0.0)/60.0
        n+=1; dem+=E; d=min(E, P*T); dlv+=d
        if E > P*T + 1e-9: fail+=1
    return dict(P=P, n_requests=n, demand_kwh=round(dem,3), ideal_delivered_kwh=round(dlv,3),
                ideal_rate=round(dlv/dem,4) if dem else None, session_failure=fail,
                session_failure_rate=round(fail/n,4) if n else None)
rows=[]
for P in (7.0,11.0,22.0,50.0):
    rows.append(ideal(ev,P)); print(rows[-1])
with open(OUT+'/ideal_bound_allsites.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
# E4 held-out streams subset
import csv as _csv
def readcsv(p):
    f=open(p,encoding='utf-8'); rs=list(_csv.DictReader(f)); f.close(); return rs
e4=readcsv(ROOT+'/experiments_main22/E4/test_E4.csv')
streams=sorted({(r['site_id'],r['day_key']) for r in e4})
print('E4 streams',len(streams),'sites',len({s for s,_ in streams}))
sub=[e for e in ev if (e['site_id'], e['arrival_ts'][:10]) in set(streams)]
print('events in held-out streams',len(sub))
res=ideal(sub,22.0); print('held-out ideal 22kW',res)
# per-stream ideal
per=defaultdict(list)
for e in ev: per[(e['site_id'], e['arrival_ts'][:10])].append(e)
prow=[]
for s,d in streams:
    r=ideal(per[(s,d)],22.0)
    prow.append({'site_id':s,'day_key':d,'n_requests':r['n_requests'],'demand_kwh':r['demand_kwh'],
                 'ideal_delivered_kwh':r['ideal_delivered_kwh'],'ideal_rate':r['ideal_rate'],
                 'session_failure':r['session_failure'],'session_failure_rate':r['session_failure_rate'],
                 'dwell_power_limited': (r['session_failure_rate'] or 0) > 0.05})
with open(OUT+'/ideal_bound_streams.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(prow[0].keys())); w.writeheader(); w.writerows(prow)
print('streams dwell/power-limited at 22kW (ideal failure rate>5%):',sum(1 for r in prow if r['dwell_power_limited']),'/',len(prow))
print('median ideal failure rate',statistics.median([r['session_failure_rate'] or 0 for r in prow]))
# ---------- 4. feeder bound per site-day ----------
sd=defaultdict(lambda: {'dem':0.0,'req':0,'site':None})
for e in ev:
    if not (e.get('is_ev') and e.get('needs_charge')): continue
    k=(e['site_id'], e['arrival_ts'][:10]); sd[k]['dem']+=float(e.get('energy_kwh') or 0); sd[k]['req']+=1; sd[k]['site']=e['site_id']
hw={s['site_id']:s for s in sites}
frow=[]
for (s,d),v in sd.items():
    feeder7=hw[s]['feeder_kw']; feeder22=hw[s]['charging_bays']*22.0
    frow.append({'site_id':s,'day_key':d,'demand_kwh':round(v['dem'],3),'requests':v['req'],'feeder_kw_7':feeder7,'feeder_kw_22':feeder22,
                 'bound_12h_7':round(feeder7*12,1),'bound_12h_22':round(feeder22*12,1),
                 'exceeds_feeder7': v['dem']>feeder7*12, 'exceeds_feeder22': v['dem']>feeder22*12})
with open(OUT+'/feeder_bound_site_days.csv','w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(frow[0].keys())); w.writeheader(); w.writerows(frow)
print('site-days with charge demand',len(frow),'exceed feeder*12h @7kW',sum(1 for r in frow if r['exceeds_feeder7']),'@22kW',sum(1 for r in frow if r['exceeds_feeder22']))
# ---------- 5. M2 independent recompute + n=20 composition ----------
metrics=['service_capacity_unmet_rate','capacity_only_unmet_rate','energy_service_rate_incl_rejected','service_departed_shortfall_energy_rate']
bys=defaultdict(dict)
for r in e4:
    key=(r['stream_id'], r['policy'])
    bys[key][ 'cap']=float(r['capacity_only_unmet_rate']); bys[key]['esr']=float(r['energy_service_rate_incl_rejected'])
paid=[(sid) for sid in {r['stream_id'] for r in e4}]
def ci(vals):
    vals=sorted(vals); k=int(0.025*len(vals)); return (round(vals[k],6), round(vals[-1-k],6), round(sum(vals)/len(vals),6))
print('n streams',len(paid))
site_of={r['stream_id']:r['site_id'] for r in e4}; day_of={r['stream_id']:r['day_key'] for r in e4}
print('distinct sites',len(set(site_of.values())),'distinct days',len(set(day_of.values())))
from collections import Counter as _C
print('streams per site',dict(_C(site_of.values())))
for base in ('B0_FCFS','B1_QUOTA','B2_LITERATURE'):
    diffs_cap=[]; diffs_esr=[]
    for sid in paid:
        a=bys[(sid,'A')]; b=bys[(sid,base)]
        diffs_cap.append(b['cap']-a['cap']); diffs_esr.append(b['esr']-a['esr'])
    print(base,'cap: mean',round(sum(diffs_cap)/len(diffs_cap),6),'CI',ci(diffs_cap),'| esr mean',round(sum(diffs_esr)/len(diffs_esr),6),'CI',ci(diffs_esr))
