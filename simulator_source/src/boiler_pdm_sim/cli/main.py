"""Command line entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from ..simulator import Simulator


def main() -> None:
    p = argparse.ArgumentParser(description="Generate boiler PdM datasets")
    p.add_argument("--config", required=True, help="path to config yaml")
    p.add_argument("--out", required=True, help="output parquet/hdf5 file path")
    p.add_argument("--format", choices=["parquet", "hdf5"], default=None)
    p.add_argument("--seed", type=int, default=None)
    args = p.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.seed is not None:
        cfg.setdefault("sim", {})["seed"] = args.seed
    if args.format is not None:
        cfg.setdefault("sim", {})["format"] = args.format

    sim = Simulator(seed=cfg.get("sim", {}).get("seed", 42))
    out = sim.run_to_file(cfg, args.out, args.format)
    print(str(out))


if __name__ == "__main__":
    main()
