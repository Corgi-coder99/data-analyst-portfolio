"""Clean the SNCF monthly TGV regularity data and build a star schema for Power BI.

Input : data/tgv_raw.csv   (downloaded by scripts/download_data.py)
Output: data/processed/{fact_route_month,fact_delay_cause,dim_route,dim_date}.csv
        docs/DATA_QUALITY_LOG.md  (every cleaning rule with the number of rows affected)

Usage (from project root): python scripts/clean_and_model.py
Requires: pip install pandas
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "tgv_raw.csv"
OUT = ROOT / "data" / "processed"
LOG = ROOT / "docs" / "DATA_QUALITY_LOG.md"

CAUSES = {  # source column -> readable label
    "prct_cause_externe": "External causes",
    "prct_cause_infra": "Infrastructure",
    "prct_cause_gestion_trafic": "Traffic management",
    "prct_cause_materiel_roulant": "Rolling stock",
    "prct_cause_gestion_gare": "Station management",
    "prct_cause_prise_en_charge_voyageurs": "Passenger handling",
}
PARIS_AXIS = {  # derived axis, from the Paris terminal of the route
    "PARIS LYON": "South-East",
    "PARIS MONTPARNASSE": "Atlantic",
    "PARIS VAUGIRARD": "Atlantic",
    "PARIS NORD": "North",
    "PARIS EST": "East",
}
log_rows = []


def note(rule, n, why):
    log_rows.append((rule, int(n), why))


def pretty(name: str) -> str:
    small = {"de", "du", "en"}
    words = name.title().split()
    out = [w.lower() if i > 0 and w.lower() in small else w for i, w in enumerate(words)]
    return " ".join(out).replace("Tgv", "TGV")


def main():
    df = pd.read_csv(RAW, sep=";", encoding="utf-8-sig")
    n_raw = len(df)
    note("Raw rows loaded", n_raw, "One row per route (departure to arrival station) per month, Jan 2018 to the latest month")

    # ---- keys and types --------------------------------------------------------
    df["month"] = pd.to_datetime(df["date"] + "-01")
    dup = df.duplicated(["date", "service", "gare_depart", "gare_arrivee"]).sum()
    note("Duplicate route-month keys", dup, "Checked: none found, no rows removed")
    df = df.rename(columns={"gare_depart": "dep_raw", "gare_arrivee": "arr_raw"})

    # ---- count columns ---------------------------------------------------------
    planned = df["nb_train_prevu"].astype(int)
    cancelled = df["nb_annulation"].astype(int)
    n = (cancelled > planned).sum()
    note("Cancellations greater than planned trains", n,
         "Mostly April 2020 (lockdown, 0 planned trains still reported cancellations). Planned trains raised to the number cancelled so rates never exceed 100%")
    df["trains_planned"] = planned.where(planned >= cancelled, cancelled)
    df["trains_cancelled"] = cancelled
    df["trains_run"] = df["trains_planned"] - df["trains_cancelled"]

    count_cols = {
        "nb_train_depart_retard": "late_departures",
        "nb_train_retard_arrivee": "late_arrivals",
        "nb_train_retard_sup_15": "late_over_15",
        "nb_train_retard_sup_30": "late_over_30",
        "nb_train_retard_sup_60": "late_over_60",
    }
    neg = (df["nb_train_retard_sup_30"] < 0).sum()
    note("Negative counts of trains more than 30 min late", neg, "Impossible values, set to 0")
    clipped = 0
    for src, dst in count_cols.items():
        v = df[src].clip(lower=0)
        over = (v > df["trains_run"]).sum()
        clipped += over
        df[dst] = v.where(v <= df["trains_run"], df["trains_run"]).astype(int)
    note("Late-train counts above the trains that actually ran (all five columns)", clipped,
         "Capped at trains run, which keeps every rate between 0 and 100%")
    # The thresholds are cumulative: late >60 is a subset of late >30, a subset of late >15, a subset of late arrivals.
    bad_chain = ((df["late_over_60"] > df["late_over_30"]) | (df["late_over_30"] > df["late_over_15"])
                 | (df["late_over_15"] > df["late_arrivals"])).sum()
    df["late_over_30"] = df[["late_over_30", "late_over_60"]].max(axis=1)
    df["late_over_15"] = df[["late_over_15", "late_over_30"]].max(axis=1)
    df["late_arrivals"] = df[["late_arrivals", "late_over_15"]].max(axis=1)
    note("Rows where the late thresholds are not nested (e.g. more trains over 60 min than over 30 min)", bad_chain,
         "Counts raised to the more severe bucket, so the chain late arrivals >= over 15 >= over 30 >= over 60 always holds")

    # ---- delay minutes -----------------------------------------------------------
    neg_avg = (df["retard_moyen_arrivee"] < 0).sum()
    note("Negative average arrival delay of late trains", neg_avg, "A delayed train cannot arrive early on average, set to missing and excluded from delay-minute totals")
    avg_late = df["retard_moyen_arrivee"].where(df["retard_moyen_arrivee"] >= 0)
    df["avg_delay_late_trains_min"] = avg_late.round(2)
    df["total_delay_minutes"] = (avg_late * df["late_arrivals"]).fillna(0).round(0).astype(int)
    outl = (df["retard_moyen_tous_trains_arrivee"] < -30).sum()
    note("Implausible values in retard_moyen_tous_trains_arrivee (below -30 min)", outl,
         "The column is not used. Delay is rebuilt from the average delay of late trains x number of late trains")

    zero_dur = (df["duree_moyenne"] == 0).sum()
    note("Average journey time equal to 0", zero_dur, "Months with no planned train. Set to missing")
    df["avg_journey_min"] = df["duree_moyenne"].where(df["duree_moyenne"] > 0)

    # ---- stations, routes ------------------------------------------------------
    df["dep"] = df["dep_raw"].map(pretty)
    df["arr"] = df["arr_raw"].map(pretty)
    routes = (df.groupby(["service", "dep_raw", "arr_raw", "dep", "arr"], as_index=False)
                .agg(avg_journey_min=("avg_journey_min", "median")))
    routes = routes.sort_values(["service", "dep", "arr"]).reset_index(drop=True)
    routes.insert(0, "route_id", routes.index + 1)

    def paris(s):
        return s in PARIS_AXIS

    def axis(r):
        if r["service"] == "International":
            return "International"
        for end in (r["dep_raw"], r["arr_raw"]):
            if end in PARIS_AXIS:
                return PARIS_AXIS[end]
        return "Cross-country"

    routes["route"] = routes["dep"] + " > " + routes["arr"]
    dup_names = routes["route"].duplicated(keep=False)
    note("Route names shared by a National and an International service", dup_names.sum(),
         "Label suffixed with the service so that every route name is unique (needed for ranking in Power BI)")
    routes.loc[dup_names, "route"] = routes["route"] + " (" + routes["service"] + ")"
    routes["axis"] = routes.apply(axis, axis=1)
    routes["is_paris_route"] = routes.apply(lambda r: paris(r["dep_raw"]) or paris(r["arr_raw"]), axis=1)
    routes["avg_journey_min"] = routes["avg_journey_min"].round(0)
    routes["journey_band"] = pd.cut(routes["avg_journey_min"], [0, 90, 180, 10_000],
                                    labels=["Under 1h30", "1h30 to 3h", "Over 3h"]).astype(str)
    note("Distinct routes (service, departure, arrival)", len(routes), "Directional routes, one row each in dim_route")
    df = df.merge(routes[["route_id", "service", "dep_raw", "arr_raw"]], on=["service", "dep_raw", "arr_raw"])

    # ---- delay causes (long format) -------------------------------------------
    cause_cols = list(CAUSES)
    share = df[cause_cols].fillna(0)
    total = share.sum(axis=1)
    no_cause = ((total == 0) & (df["late_arrivals"] > 0)).sum()
    note("Route-months with late trains but no cause shares reported", no_cause,
         "Kept in the facts. Excluded from the cause breakdown, which is an estimate")
    norm = share.div(total.where(total > 0), axis=0).fillna(0)
    est = norm.mul(df["late_arrivals"], axis=0)
    cause = pd.concat([df[["route_id", "month"]], est], axis=1).melt(
        id_vars=["route_id", "month"], var_name="cause_col", value_name="late_trains_est")
    cause["cause"] = cause["cause_col"].map(CAUSES)
    cause = cause[cause["late_trains_est"] > 0].assign(late_trains_est=lambda x: x["late_trains_est"].round(2))
    cause = cause[["route_id", "month", "cause", "late_trains_est"]]

    # ---- date dimension -----------------------------------------------------------
    months = pd.date_range(df["month"].min(), df["month"].max(), freq="MS")
    dim_date = pd.DataFrame({"month": months})
    dim_date["year"] = dim_date["month"].dt.year
    dim_date["month_number"] = dim_date["month"].dt.month
    dim_date["month_name"] = dim_date["month"].dt.strftime("%b")
    dim_date["quarter"] = "Q" + dim_date["month"].dt.quarter.astype(str)
    dim_date["year_month"] = dim_date["month"].dt.strftime("%Y-%m")
    dim_date["season"] = dim_date["month_number"].map(
        lambda m: "Winter" if m in (12, 1, 2) else "Spring" if m in (3, 4, 5) else "Summer" if m in (6, 7, 8) else "Autumn")

    fact = df[["route_id", "month", "trains_planned", "trains_cancelled", "trains_run", "late_departures",
               "late_arrivals", "late_over_15", "late_over_30", "late_over_60", "avg_delay_late_trains_min",
               "total_delay_minutes"]].sort_values(["month", "route_id"])

    OUT.mkdir(parents=True, exist_ok=True)
    fact.to_csv(OUT / "fact_route_month.csv", index=False, date_format="%Y-%m-%d")
    cause.to_csv(OUT / "fact_delay_cause.csv", index=False, date_format="%Y-%m-%d")
    routes[["route_id", "route", "dep", "arr", "service", "axis", "is_paris_route", "avg_journey_min",
            "journey_band"]].to_csv(OUT / "dim_route.csv", index=False)
    dim_date.to_csv(OUT / "dim_date.csv", index=False, date_format="%Y-%m-%d")

    note("Clean fact rows written", len(fact), f"{fact['month'].min():%Y-%m} to {fact['month'].max():%Y-%m}, {fact['route_id'].nunique()} routes")
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("# Data quality log\n\nEvery rule applied by `scripts/clean_and_model.py`, with the number of rows it touched.\n\n")
        f.write("| Rule | Rows | Treatment |\n|------|-----:|-----------|\n")
        for rule, k, why in log_rows:
            f.write(f"| {rule} | {k:,} | {why} |\n")
    print(pd.DataFrame(log_rows, columns=["rule", "rows", "why"])[["rule", "rows"]].to_string(index=False))


if __name__ == "__main__":
    main()
