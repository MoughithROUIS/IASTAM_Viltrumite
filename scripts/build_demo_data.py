"""Regenerates demo/data/*.js from the recorded results (no network, no extra dependencies).
Run from the repository root:  python3 scripts/build_demo_data.py"""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
trace = json.load(open(root / "results" / "demo_data.json"))
ext = json.load(open(root / "results" / "multiseed_extended.json"))
ms = {"n_seeds": ext["n_seeds"], "levels": ext["levels"], "baseline": ext["baseline"], "sweep": ext["sweep"]}
out = root / "demo" / "data"
out.mkdir(parents=True, exist_ok=True)
(out / "demo-data.js").write_text("const DEMO_DATA = " + json.dumps(trace, separators=(",", ":")) + ";\n")
(out / "results-data.js").write_text("const MS = " + json.dumps(ms, separators=(",", ":")) + ";\n")
print("wrote demo/data/demo-data.js and demo/data/results-data.js")
