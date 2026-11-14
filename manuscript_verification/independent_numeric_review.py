from pathlib import Path
import json,csv,numpy as np,re
R=Path(__file__).resolve().parent
D=R/'evidence/r2/data';O=R/'numeric';O.mkdir(exist_ok=True)
methods={'B0_state':('state_score','available_state'),'Flow_only':('flow_z','available_flow_command'),'Command_only':('command_z','available_flow_command'),'B1_combined':('combined_score','available_flow_command')}
meta=list(csv.DictReader((D/'episode_metadata.csv').open()))
tr={m['episode']:dict(np.load(D/'traces'/f"{m['episode']}.npz",allow_pickle=False)) for m in meta}
obs={m['episode']:dict(np.load(D/'observations'/f"{m['episode']}.npz",allow_pickle=False)) for m in meta}
def runs(mask):
 idx=np.flatnonzero(np.diff(np.r_[False,mask,False].astype(int)))
 return list(zip(idx[::2],idx[1::2]-1))
def alarms(d,key,available,th):
 t=d['time']; s=d[key]; m=(t>=1200)&d[available]&np.isfinite(s)&(s>th);out=[]
 for a,b in runs(m):
  due=t[a]+600
  if out: due=max(due,out[-1]+1800)
  while due <= t[b]+1e-9:
   k=int(np.searchsorted(t,due-1e-9)); out.append(float(t[k]));due=t[k]+1800
 return out
cands=[];settings={}
for name,(key,av) in methods.items():
 vals=np.concatenate([tr[f'D{i}_normal'][key][(tr[f'D{i}_normal']['time']>=1200)&tr[f'D{i}_normal'][av]] for i in range(1,5)])
 for q in (.99,.995,.999,.9995,1):
  v=float(np.quantile(vals,q,method='linear'));ns=[len(alarms(tr[f'D{i}_normal'],key,av,v)) for i in range(1,5)]
  cands.append({'method':name,'quantile':q,'threshold':v,'counts':ns})
  if name not in settings and sum(ns)==0:settings[name]=v
records=[];checks=[];margins=[]
for m in meta:
 name=m['episode']; d=tr[name];o=obs[name];t=d['time'];start=confirm=None
 for a,b in runs((o['meta/fw_cmd']>=.95)&(o['truth/drum_level']<=.75)):
  if t[b]-t[a]>=120:
   start=float(t[a]);confirm=float(t[np.searchsorted(t,t[a]+120)]);break
 onset=float(m['onset_s']) if m['onset_s'] else None
 for method,(key,av) in methods.items():
  al=alarms(d,key,av,settings[method]);after=[x for x in al if onset is not None and x>=onset and x<(confirm or t[-1])];first=after[0] if after else None
  records.append({'episode':name,'method':method,'first_post_onset_alarm_s':first,'delay_min':(first-onset)/60 if first is not None else None,'strict_lead_min':(start-first)/60 if first is not None and start is not None else None,'event_start_s':start,'event_confirm_s':confirm,'all_alarm_times_s':al,'normal_alarms':len(al) if onset is None else None})
  if onset is None:
   mask=(t>=1200)&d[av]&np.isfinite(d[key])&(d[key]>settings[method]);spans=[float(t[b]-t[a]) for a,b in runs(mask)]
   margins.append({'episode':name,'method':method,'max_exceedance_span_s':max(spans,default=0),'score_max':float(d[key][(t>=1200)&d[av]].max())})
old=list(csv.DictReader((R/'evidence/r2/results/episode_method_results.csv').open()))
for r in records:
 v=next(x for x in old if x['episode']==r['episode'] and x['method']==r['method'])
 good=(json.loads(v['all_alarm_times_s'])==r['all_alarm_times_s'])
 for k,new in [('functional_start_s',r['event_start_s']),('functional_confirm_s',r['event_confirm_s'])]:
  val=float(v[k]) if v[k] else None;good &= val==new
 checks.append({'episode':r['episode'],'method':r['method'],'alarm_and_event_match':bool(good)})
summary=[]
for method in methods:
 normal=[r for r in records if r['episode'].startswith('E') and r['episode'].endswith('normal') and r['method']==method]
 fault=[r for r in records if r['episode'].startswith('E') and r['episode'].endswith('tube_leak') and r['method']==method]
 delays=np.array([x['delay_min'] for x in fault]);lead=np.array([x['strict_lead_min'] for x in fault if x['strict_lead_min'] is not None])
 summary.append({'method':method,'threshold':settings[method],'normal_alarm_count':sum(r['normal_alarms'] for r in normal),'fault_n':len(fault),'event_n':len(lead),'delay_median_min':float(np.median(delays)),'delay_min':float(delays.min()),'delay_max':float(delays.max()),'lead_median_min':float(np.median(lead)),'lead_min':float(lead.min()),'lead_max':float(lead.max())})
# Check rendered scientific table quantities against independently reconstructed summaries.
struct=json.loads((R/'evidence/docx_structure.json').read_text()); tables={t['id']:t['rows'] for t in struct if t['type']=='table'}
tabchecks=[]
for row,expected in zip(tables['T20'][1:],summary):
 actual=[float(x.replace(',','')) for x in re.findall(r'\d+(?:\.\d+)?',row[3]+' '+row[4])]
 target=[round(expected[k],1) for k in ['delay_median_min','delay_min','delay_max','lead_median_min','lead_min','lead_max']]
 tabchecks.append({'table':'6','row':row[0],'match':actual==target,'actual':actual,'expected':target})
for row in tables['T22'][1:]:
 block=row[0].split()[0]; vals=[float(x.replace('a','')) for x in row[2:]]
 expected=[next(x['max_exceedance_span_s'] for x in margins if x['episode']==block+'_normal' and x['method']==m) for m in methods]
 tabchecks.append({'table':'8','row':block,'match':vals==expected,'actual':vals,'expected':expected})
# Empirical sufficient condition and counterexample for the claimed max-score quantile identity.
F=np.concatenate([tr[f'D{i}_normal']['flow_z'][tr[f'D{i}_normal']['time']>=1200] for i in range(1,5)])
C=np.concatenate([tr[f'D{i}_normal']['command_z'][tr[f'D{i}_normal']['time']>=1200] for i in range(1,5)])
a=np.zeros(1000);b=np.zeros(1000);a[:9]=10;b[9:18]=11
quantile={'observed_max_flow':float(F.max()),'observed_q99_flow':float(np.quantile(F,.99)),'observed_q99_demand':float(np.quantile(C,.99)),'observed_q99_max':float(np.quantile(np.maximum(F,C),.99)), 'counterexample':{'q':.99,'F_nonzero':9,'D_nonzero':9,'disjoint_positions':True,'Q_F':float(np.quantile(a,.99)),'Q_D':float(np.quantile(b,.99)),'Q_max':float(np.quantile(np.maximum(a,b),.99))}}
# Stronger counterexample with Q_D > Q_F and Q_max > Q_D
b=np.ones(1000);b[9:18]=11
quantile['counterexample_strict']={'Q_F':float(np.quantile(a,.99)),'Q_D':float(np.quantile(b,.99)),'Q_max':float(np.quantile(np.maximum(a,b),.99))}
for filename,items in [('summary.csv',summary),('episode_results.csv',records),('normal_persistence.csv',margins),('recomputed_vs_archived.csv',checks),('manuscript_table_checks.csv',tabchecks)]:
 with (O/filename).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=items[0].keys());w.writeheader();w.writerows(items)
(O/'quantile_claim_check.json').write_text(json.dumps(quantile,indent=2))
info={'episodes':len(meta),'timestamps':sum(len(v['time']) for v in tr.values()),'episode_method_comparisons':len(checks),'matches':sum(c['alarm_and_event_match'] for c in checks),'manuscript_table6_8_row_checks':len(tabchecks),'row_matches':sum(c['match'] for c in tabchecks),'threshold_candidates':cands,'simulation_run':False,'analysis': 'independent interval-based replay from saved traces and raw event channels; feature extraction not rerun'}
(O/'review_execution_summary.json').write_text(json.dumps(info,indent=2))
print(json.dumps({'info':{k:v for k,v in info.items() if k!='threshold_candidates'},'summary':summary,'quantile':quantile},indent=2))
