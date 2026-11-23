"""Build the self-contained HTML dashboard (dashboard/index.html) from the processed tables.

Usage (from project root): python scripts/build_dashboard.py
Requires: pip install pandas
Run scripts/clean_and_model.py first.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data" / "processed"
AXES = ["Atlantic", "South-East", "North", "East", "Cross-country", "International"]
BANDS = ["Under 1h30", "1h30 to 3h", "Over 3h"]


def main():
    fact = pd.read_csv(P / "fact_route_month.csv", parse_dates=["month"])
    route = pd.read_csv(P / "dim_route.csv")
    cause = pd.read_csv(P / "fact_delay_cause.csv", parse_dates=["month"])
    dim_date = pd.read_csv(P / "dim_date.csv")

    months = dim_date["year_month"].tolist()
    m_idx = {m: i for i, m in enumerate(months)}
    route = route.reset_index(drop=True)
    r_idx = {rid: i for i, rid in enumerate(route["route_id"])}
    causes = sorted(cause["cause"].unique(), key=lambda c: ["External causes", "Traffic management", "Infrastructure",
                                                            "Rolling stock", "Station management", "Passenger handling"].index(c))
    wide = (cause.pivot_table(index=["route_id", "month"], columns="cause", values="late_trains_est", aggfunc="sum")
                 .reindex(columns=causes).fillna(0))
    fact = fact.merge(wide.reset_index(), on=["route_id", "month"], how="left").fillna({c: 0 for c in causes})

    fact["r"] = fact["route_id"].map(r_idx)
    fact["m"] = fact["month"].dt.strftime("%Y-%m").map(m_idx)
    base = ["r", "m", "trains_planned", "trains_cancelled", "trains_run", "late_arrivals", "late_over_15",
            "late_over_30", "late_over_60", "total_delay_minutes"]
    ints = fact[base].astype(int).to_numpy().tolist()
    cvals = fact[causes].round(1).to_numpy().tolist()
    rows = [a + c for a, c in zip(ints, cvals)]

    data = {
        "months": months,
        "axes": AXES,
        "bands": BANDS,
        "causes": causes,
        "routes": [{"n": x.route, "s": 1 if x.service == "International" else 0, "a": AXES.index(x.axis),
                    "j": BANDS.index(x.journey_band)} for x in route.itertuples()],
        "rows": rows,
    }
    tpl = (ROOT / "dashboard" / "template.html").read_text(encoding="utf-8")
    out = tpl.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    (ROOT / "dashboard" / "index.html").write_text(out, encoding="utf-8")
    print(f"dashboard/index.html written: {len(out) / 1e6:.2f} MB, {len(rows)} rows, {len(route)} routes")


if __name__ == "__main__":
    main()
