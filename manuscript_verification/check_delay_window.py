"""Compare recorded pre-terminal first alarms with first alarms through the horizon."""
import csv
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile

src, dst = map(Path,sys.argv[1:])
with ZipFile(src) as z:
    prefix = next(n.removesuffix("results/episode_method_results.csv") for n in z.namelist()
                  if n.endswith("/results/episode_method_results.csv"))
    def table(member):
        return csv.DictReader(io.StringIO(z.read(prefix + member).decode("utf-8-sig")))
    metadata = {r["episode"]: r for r in table("data/episode_metadata.csv")}
    out = []
    for row in table("results/episode_method_results.csv"):
        if row["split"] != "evaluation" or row["branch"] != "tube_leak":
            continue
        onset = float(metadata[row["episode"]]["onset_s"])
        first = next((s for s in json.loads(row["all_alarm_times_s"]) if s >= onset), None)
        reported = float(row["first_post_onset_alarm_s"]) if row["first_post_onset_alarm_s"] else None
        out.append(dict(episode=row["episode"],method=row["method"],onset_s=onset,
                        functional_confirm_s=row["functional_confirm_s"],first_preterminal_s=reported,
                        first_over_full_trace_after_onset_s=first,identical=reported==first))
with dst.open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
assert len(out)==32 and all(r["identical"] for r in out)
