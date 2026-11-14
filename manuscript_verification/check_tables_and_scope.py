from pathlib import Path
import json, csv, re, numpy as np, hashlib, zipfile
from docx import Document
R=Path(__file__).resolve().parent; D=R/'evidence/r2/data';O=R/'numeric'
t={x['id']:x['rows'] for x in json.loads((R/'evidence/docx_structure.json').read_text()) if x['type']=='table'}
fit=json.loads((R/'evidence/r2/results/independent_fit.json').read_text());b={v['block']:v for v in json.loads((D/'block_design.json').read_text())['blocks']}
summary=json.loads((O/'review_execution_summary.json').read_text());rows=[]
parse=lambda s: None if '—' in s else float(re.sub(r'[ab]$','',s).replace(',','').replace('−','-'))
for x in t['T12'][1:]:
 v=b[x[0]]; cfg=json.loads((D/'original_configs'/f"{x[0]}_normal_config_applied.json").read_text());expected=[v['regime'],cfg['sim']['seed'],v['fault']['onset_s'],v['fault']['duration_s'],v['fault']['k_leak_kg_s_per_sqrtbar']];actual=[parse(y) for y in x[2:]]
 rows.append({'table':3,'row':x[0],'kind':'configuration cross-check','match':all(abs(u-v)<1e-8 for u,v in zip(actual,expected)),'actual':actual,'expected':expected})
expected=fit['ref_rM']+fit['ref_fw']+[fit['sigma_rM'],fit['sigma_fw'],fit['sigma_level'],fit['sigma_pressure'],fit['fit_rows']]
for x,v in zip(t['T18'][1:],expected):
 u=parse(x[1]);rows.append({'table':4,'row':x[0],'kind':'archived fit cross-check','match':bool(np.isclose(u,v,rtol=1e-11,atol=1e-12)),'actual':u,'expected':v})
method_map={'State (B0)':'B0_state','Flow only':'Flow_only','Demand only':'Command_only','Combined (B1)':'B1_combined'}
for x in t['T19'][1:]:
 method=method_map[x[0].replace(' [Retained]','')];q=float(x[2]);v=next(z for z in summary['threshold_candidates'] if z['method']==method and z['quantile']==q)
 actual=[parse(x[3])]+[int(y) for y in x[4:]];exp=[round(v['threshold'],6)]+v['counts'];rows.append({'table':5,'row':x[0]+':'+x[2],'kind':'independently recomputed thresholds and alarms','match':actual==exp,'actual':actual,'expected':exp})
metrics=list(csv.DictReader((O/'episode_results.csv').open(encoding='utf-8-sig')))
for x in t['T21'][1:]:
 block=x[0];name=block+'_tube_leak';z={v['method']:v for v in metrics if v['episode']==name};cfg=json.loads((D/'original_configs'/f'{name}_config_applied.json').read_text()); ob=dict(np.load(D/'observations'/f'{name}.npz',allow_pickle=False));time=ob['time']
 def first(mask):
  w=np.flatnonzero(mask); return float(time[w[0]]) if len(w) else None
 actual=[parse(y) for y in x[1:]];v=z['B1_combined'];exp=[b[block]['fault']['onset_s']]+[float(z[m]['first_post_onset_alarm_s']) for m in method_map.values()]+[float(v[k]) if v[k] else None for k in ['event_start_s','event_confirm_s']]+[first(ob['meta/safety_state']=='trip'),first(ob['truth/state_feasible']<=0)]
 rows.append({'table':7,'row':block,'kind':'independently recomputed alarms and raw events','match':actual==exp,'actual':actual,'expected':exp})
with (O/'tables_3_4_5_7_crosscheck.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
# supplement event sensitivity: counts and why fixed-alarm rank cannot independently test endpoint robustness.
sens=list(csv.DictReader((R/'evidence/r2/results/endpoint_sensitivity.csv').open()))
sens_counts={str(c):sum(v['observed']=='True' for v in sens if v['split']=='evaluation' and float(v['level_cutoff_m'])==c) for c in [.7,.75,.8]}
record={'table_rows_checked':len(rows),'matched':sum(x['match'] for x in rows),'rounding_corrections':{'difference_of_delay_medians_min':127.26666666666668-75.93333333333334,'display_to_1dp':51.3,'max_demand_and_combined_delay_min':(11762-4830)/60,'display_max_to_1dp':115.5},'endpoint_sensitivity_observed_count':sens_counts}
(O/'tables_and_rounding_summary.json').write_text(json.dumps(record,indent=2))
print(json.dumps(record,indent=2));print([x for x in rows if not x['match']])
# scope and exact input identity
p=Path('/mnt/data/PUB053_Manuscript_JMSE_Submission.docx');d=Document(p);raw=zipfile.ZipFile(p); ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
xml=raw.read('word/document.xml').decode();abstract=d.paragraphs[6].text.removeprefix('Abstract:')
layout={'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'abstract_space_delimited_words':len(abstract.split()),'document_paragraphs':len(d.paragraphs),'scientific_numbered_tables':8,'figures':7,'reference_entries':27,'equation_number_groups':13,'equation_expressions':16,'section_bidi_present':bool(d.element.xpath('.//w:sectPr/w:bidi')),'rendered_pages_libreoffice':35,'office_cached_page_count':re.search(r'<Pages>(\d+)</Pages>',raw.read('docProps/app.xml').decode()).group(1),'input_modified':False}
(R/'evidence/final_scope_and_identity.json').write_text(json.dumps(layout,indent=2));print(layout)
