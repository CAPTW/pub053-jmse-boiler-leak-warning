"""Check strict leads on recorded R2 data. Run with R2 ZIP and output directory."""
import argparse
import csv
import io
from pathlib import Path
import statistics
from zipfile import ZipFile

import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("r2_zip", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
args.output.mkdir(exist_ok=True, parents=True)

def table(z, member):
    return list(csv.DictReader(io.StringIO(z.read(member).decode("utf-8-sig"))))

def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

out = []
summary = []
with ZipFile(args.r2_zip) as z:
    prefix = next(n.removesuffix("results/episode_method_results.csv") for n in z.namelist()
                  if n.endswith("/results/episode_method_results.csv"))
    alarms = {(r["episode"], r["method"]): int(float(r["first_post_onset_alarm_s"]))
              for r in table(z, prefix + "results/episode_method_results.csv")
              if r["split"] == "evaluation" and r["branch"] == "tube_leak"}
    endpoints = {(r["episode"],float(r["level_cutoff_m"])): r
                 for r in table(z, prefix + "results/endpoint_sensitivity.csv")}
    for i in range(1,9):
        ep = f"E{i}_tube_leak"
        with np.load(io.BytesIO(z.read(prefix + f"data/observations/{ep}.npz")), allow_pickle=False) as traj:
            times = traj["time"]
            assert np.all(np.diff(times) == 2)
            for cutoff in (0.70, 0.75, 0.80):
                good = (traj["meta/fw_cmd"] >= 0.95) & (traj["truth/drum_level"] <= cutoff)
                ix = np.flatnonzero(np.convolve(good.astype(int), np.ones(61, dtype=int), "valid") == 61)
                start = int(times[ix[0]]) if len(ix) else None
                record = endpoints[(ep,cutoff)]["functional_start_s"]
                assert (int(float(record)) if record else None) == start
                for method in ("B0_state","Flow_only","Command_only","B1_combined"):
                    alarm = alarms[ep,method]
                    out.append(dict(episode=ep,level_cutoff_m=cutoff,method=method,
                                    functional_start_s=start,alarm_s=alarm,
                                    strict_lead_s=None if start is None else start-alarm))
for cutoff in (0.70,0.75,0.80):
    for method in ("B0_state","Flow_only","Command_only","B1_combined"):
        leads = [r["strict_lead_s"] for r in out if r["level_cutoff_m"] == cutoff and r["method"] == method
                 and r["strict_lead_s"] is not None]
        summary.append(dict(level_cutoff_m=cutoff, method=method, n_observed=len(leads), n_positive=sum(t>0 for t in leads),
                            median_strict_lead_s=statistics.median(leads), median_strict_lead_min=statistics.median(leads)/60))
write(args.output/"cutoff_leads_by_block.csv",out)
write(args.output/"cutoff_leads_summary.csv",summary)
