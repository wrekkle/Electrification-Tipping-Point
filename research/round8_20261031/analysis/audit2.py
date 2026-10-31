# -*- coding: utf-8 -*-
import json,csv,sys,statistics,random
from collections import defaultdict, Counter
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT='research/round8_20261031'; OUT=ROOT+'/analysis'
def rc(p):
    f=open(p,encoding='utf-8'); rs=list(csv.DictReader(f)); f.close(); return rs
w=rc(ROOT+'/data/processed/_window_events.csv')
c=json.load(open(ROOT+'/data/processed/public_parking_events.json',encoding='utf-8'))
sel={s['site_id'] for s in c['sites']}
print('window rows',len(w),'contract events',len({e['event_id'] for e in c['events']}))
open_sess=[r for r in w if not r['dep_local'] or r['dep_local'].startswith('1900')]
print('window rows with missing/1900 departure:',len(open_sess),'their dwell_min values:',Counter(r['dwell_min'] for r in open_sess).most_common(3))
rows_sel=[r for r in w if r['area'] in sel]
print('window rows in selected 10 areas:',len(rows_sel),'| areas present:',len({r['area'] for r in w}),'selected:',len(sel))
bad=[r for r in rows_sel if (not r['dep_local']) or r['dep_local'].startswith('1900') or (r['dwell_min'] and float(r['dwell_min'])<=0)]
print('selected-area rows with invalid/zero dwell or open session:',len(bad))
kept=len(rows_sel)-len(bad); print('expected kept',kept,'actual',len(c['events']),'diff',kept-len(c['events']))
print('events per selected area vs window rows:')
wc=Counter(r['area'] for r in rows_sel); cc=Counter(e['site_id'] for e in c['events'])
for s in sorted(sel): print(' ',s,'window',wc[s],'contract',cc[s],'diff',wc[s]-cc[s])
# dates
days=Counter(r['day_local'] for r in rows_sel); print('selected-area local days',len(days),'min',min(days),'max',max(days))
print('all-window local days',len({r['day_local'] for r in w}))
# concurrency minutes fix
from datetime import datetime
by=defaultdict(list)
for r in rows_sel:
    if r['dep_local'] and not r['dep_local'].startswith('1900'): by[r['area']].append((r['arr_local'],r['dep_local']))
for s in sorted(sel):
    ev=sorted([(a,1) for a,d in by[s]]+[(d,-1) for a,d in by[s]])
    cur=0; mx=0; over=0.0; prev=None; nsp=next(x['n_spaces'] for x in c['sites'] if x['site_id']==s)
    for t,dl in ev:
        if prev is not None:
            dt=(datetime.fromisoformat(t)-datetime.fromisoformat(prev)).total_seconds()/60.0
            if cur>nsp: over+=dt
        cur+=dl; mx=max(mx,cur); prev=t
    print('CONC',s,'n_spaces',nsp,'max',mx,'minutes_over',round(over,1))
# n=20 composition and bootstrap
e4=rc(ROOT+'/experiments_main22/E4/test_E4.csv')
byk={(r['stream_id'],r['policy']):r for r in e4}
streams=sorted({r['stream_id'] for r in e4}); site={r['stream_id']:r['site_id'] for r in e4}
def boot(diffs, B=1000, seed=20261031):
    rng=random.Random(seed); n=len(diffs); means=[]
    for _ in range(B): means.append(sum(diffs[rng.randrange(n)] for _ in range(n))/n)
    means.sort(); return (round(means[int(0.025*B)],6), round(means[int(0.975*B)-1],6), round(sum(diffs)/n,6))
def boot_cluster(groups, B=1000, seed=20261031):
    rng=random.Random(seed); keys=list(groups); means=[]
    for _ in range(B):
        samp=[keys[rng.randrange(len(keys))] for _ in range(len(keys))]
        vals=[v for k in samp for v in groups[k]]
        means.append(sum(vals)/len(vals))
    means.sort(); allv=[x for g in groups.values() for x in g]; return (round(means[int(0.025*B)],6), round(means[int(0.975*B)-1],6), round(sum(allv)/len(allv),6))
for base in ('B0_FCFS','B1_QUOTA','B2_LITERATURE'):
    diffs=[float(byk[(s,base)]['energy_service_rate_incl_rejected'])-float(byk[(s,'A')]['energy_service_rate_incl_rejected']) for s in streams]
    g=defaultdict(list)
    for s,d in zip(streams,diffs): g[site[s]].append(d)
    print('M2',base,'stream-boot',boot(diffs),'site-cluster-boot',boot_cluster(g),'n_clusters',len(g))
# B1 vs B2 per stream differences
same=sum(1 for s in streams if byk[(s,'B1_QUOTA')]['energy_service_rate_incl_rejected']==byk[(s,'B2_LITERATURE')]['energy_service_rate_incl_rejected'])
print('B1==B2 energy rates: ',same,'/',len(streams),'| cap equal:',sum(1 for s in streams if byk[(s,'B1_QUOTA')]['capacity_only_unmet_rate']==byk[(s,'B2_LITERATURE')]['capacity_only_unmet_rate']))