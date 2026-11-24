"""Generate a Power BI Project (PBIP) with the semantic model already built.

What you get: 4 tables loaded from data/processed/*.csv, the 4 relationships, a date table, hidden raw
columns, and every DAX measure from powerbi/measures.dax (single source of truth, parsed here).
The data is embedded in the model (compressed inline M), so nothing depends on a file path.
The report has the three empty pages (Home, Overview, Routes & Causes): you add the visuals.

Usage (from project root):  python scripts/make_pbip.py
Then open powerbi/TGV_Punctuality.pbip in Power BI Desktop.
Needs Power BI Desktop with the "Power BI Project (.pbip) save option" preview feature enabled
(File > Options and settings > Options > Preview features).
"""
import base64
import csv
import json
import re
import uuid
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
OUT = ROOT / "powerbi"
NAME = "TGV_Punctuality"
SM = OUT / f"{NAME}.SemanticModel"
RP = OUT / f"{NAME}.Report"

# column -> (TMDL dataType, M type, format, hidden)
INT = ("int64", "Int64.Type", "#,0", True)
TYPES = {
    "route_id": ("int64", "Int64.Type", "0", True),
    "month": ("dateTime", "type date", "yyyy-mm-dd", False),
    "avg_delay_late_trains_min": ("double", "type number", "0.0", True),
    "avg_journey_min": ("double", "type number", "0", False),
    "late_trains_est": ("double", "type number", "#,0.0", True),
    "is_paris_route": ("boolean", "type logical", None, False),
    "year": ("int64", "Int64.Type", "0", False),
    "month_number": ("int64", "Int64.Type", "0", False),
    "cause": ("string", "type text", None, False),
}
FACT_INT = ["trains_planned", "trains_cancelled", "trains_run", "late_departures", "late_arrivals", "late_over_15",
            "late_over_30", "late_over_60", "total_delay_minutes"]
STRINGS = ["route", "dep", "arr", "service", "axis", "journey_band", "month_name", "quarter", "year_month", "season", "cause"]
TABLES = ["fact_route_month", "fact_delay_cause", "dim_route", "dim_date"]


def guid():
    return str(uuid.uuid4())


def col_type(table, col):
    if col in TYPES:
        dt, mt, fmt, hidden = TYPES[col]
    elif col in FACT_INT:
        dt, mt, fmt, hidden = INT
    else:
        dt, mt, fmt, hidden = "string", "type text", None, False
    if table.startswith("dim_") and col == "route_id":
        hidden = False  # the dimension key stays visible, the fact-table copy is hidden
    if table.startswith("fact_") and col == "month":
        hidden = True
    return dt, mt, fmt, hidden


def header(table):
    with open(PROC / f"{table}.csv", encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


def table_tmdl(table):
    cols = header(table)
    lines = [f"table {table}", f"\tlineageTag: {guid()}"]
    if table == "dim_date":
        lines.append("\tdataCategory: Time")
    lines.append("")
    for c in cols:
        dt, mt, fmt, hidden = col_type(table, c)
        lines.append(f"\tcolumn {c}")
        lines.append(f"\t\tdataType: {dt}")
        if hidden:
            lines.append("\t\tisHidden")
        if table == "dim_date" and c == "month":
            lines.append("\t\tisKey")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines.append(f"\t\tlineageTag: {guid()}")
        lines.append("\t\tsummarizeBy: " + ("sum" if dt in ("int64", "double") and hidden and not c.endswith("_id") else "none"))
        lines.append(f"\t\tsourceColumn: {c}")
        if table == "dim_date" and c == "month_name":
            lines.append("\t\tsortByColumn: month_number")
        lines.append("")
    types = ", ".join('{"%s", %s}' % (c, col_type(table, c)[1]) for c in cols)
    raw = (PROC / f"{table}.csv").read_bytes()
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate, the same as M Compression.Deflate
    b64 = base64.b64encode(deflate.compress(raw) + deflate.flush()).decode("ascii")
    lines += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
              f'					Source = Csv.Document(Binary.Decompress(Binary.FromText("{b64}", BinaryEncoding.Base64), Compression.Deflate), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
              "\t\t\t\t\tPromoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),",
              f'\t\t\t\t\tTyped = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
              "\t\t\t\tin", "\t\t\t\t\tTyped", "", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(lines)


def split_grouped(text):
    """measures.dax groups single-line measures without blank lines; split on lines of the form 'Name = expr'."""
    out, cur = [], None
    for raw in text.split("\n"):
        line = re.sub(r"\s*//.*$", "", raw).rstrip()
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z_][^=\n]*?)\s*=\s*(.*)$", line) if not line.startswith((" ", "\t", ")")) else None
        if m and not line.startswith(("VAR", "RETURN")):
            cur = [m.group(1).strip(), [m.group(2).strip()] if m.group(2).strip() else []]
            out.append(cur)
        elif cur is not None:
            cur[1].append(line)
    return [(n, b) for n, b in out]


def fmt_for(name):
    n = name.lower()
    if "yoy" in n:
        return "+0.0%;-0.0%"
    if "rate" in n and "rank" not in n and "colour" not in n or "share" in n:
        return "0.0%"
    if "avg delay" in n:
        return "0.0"
    if "rank" in n:
        return "0"
    if any(k in n for k in ("trains", "late over", "arrivals", "minutes", "hours")) and "headline" not in n:
        return "#,0"
    return None


OUTCOMES = ["On time", "Late, under 15 min", "Late 15 to 30 min", "Late 30 to 60 min", "Late over 60 min", "Cancelled"]


def outcome_table():
    rows = ", ".join('{"%s", %d}' % (o, i + 1) for i, o in enumerate(OUTCOMES))
    T = "\t"
    return "\n".join([
        "table Outcome", f"{T}lineageTag: {guid()}", "",
        f"{T}column Outcome", f"{T}{T}dataType: string", f"{T}{T}lineageTag: {guid()}", f"{T}{T}summarizeBy: none",
        f"{T}{T}sourceColumn: Outcome", f"{T}{T}sortByColumn: Order", "",
        f"{T}column Order", f"{T}{T}dataType: int64", f"{T}{T}isHidden", f"{T}{T}lineageTag: {guid()}",
        f"{T}{T}summarizeBy: none", f"{T}{T}sourceColumn: Order", "",
        f"{T}partition Outcome = m", f"{T}{T}mode: import", f"{T}{T}source =", f"{T}{T}{T}{T}let",
        f'{T}{T}{T}{T}{T}Source = #table(type table [Outcome = text, Order = Int64.Type], {{{rows}}})', f"{T}{T}{T}{T}in", f"{T}{T}{T}{T}{T}Source", ""])


def measures_table():
    text = (OUT / "measures.dax").read_text(encoding="utf-8")
    items = split_grouped(text)
    lines = ["table _Measures", f"\tlineageTag: {guid()}", "", "\tcolumn Dummy", "\t\tdataType: int64", "\t\tisHidden",
             "\t\tformatString: 0", f"\t\tlineageTag: {guid()}", "\t\tsummarizeBy: none", "\t\tsourceColumn: Dummy", ""]
    for name, body in items:
        q = f"'{name}'" if re.search(r"[^A-Za-z0-9_]", name) else name
        if len(body) == 1:
            lines.append(f"\tmeasure {q} = {body[0]}")
        else:
            lines.append(f"\tmeasure {q} =")
            for b in body:
                lines.append("\t\t\t" + b)
        f = fmt_for(name)
        if f:
            lines.append(f"\t\tformatString: {f}")
        lines.append(f"\t\tlineageTag: {guid()}")
        lines.append("")
    lines += ["	partition _Measures = m", "		mode: import", "		source =", "				let",
              "					Source = #table(type table [Dummy = Int64.Type], {{1}})", "				in", "					Source", ""]
    return "\n".join(lines), [n for n, _ in items]


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


# ----------------------------------------------------------------------------- report visuals (PBIR)
def L(text):
    return {"expr": {"Literal": {"Value": "'" + text.replace("'", "''") + "'"}}}


def LB(v):
    return {"expr": {"Literal": {"Value": "true" if v else "false"}}}


def col(entity, prop):
    return ({"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}, f"{entity}.{prop}", prop)


def meas(name):
    return ({"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": name}}, f"_Measures.{name}", name)


def proj(f):
    return {"field": f[0], "queryRef": f[1], "nativeQueryRef": f[2]}


class Page:
    def __init__(self, pid):
        self.pid, self.n = pid, 0

    def add(self, x, y, w, h, vis, filters=None):
        self.n += 1
        name = f"v{self.n:02d}"
        c = {"$schema": "%s/visualContainer/1.0.0/schema.json" % BASE_URL, "name": name,
             "position": {"x": x, "y": y, "z": self.n, "height": h, "width": w, "tabOrder": self.n * 100}, "visual": vis}
        if filters:
            c["filterConfig"] = {"filters": filters}
        write(RP / "definition" / "pages" / self.pid / "visuals" / name / "visual.json", json.dumps(c, indent=2))


BASE_URL = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def num(v):
    return {"expr": {"Literal": {"Value": f"{v}D"}}}


CARD_OBJ = {"labels": [{"properties": {"fontSize": num(26), "labelDisplayUnits": num(1)}}],
            "categoryLabels": [{"properties": {"show": LB(False)}}]}
DONUT_OBJ = {"labels": [{"properties": {"labelStyle": L("Percent of total"), "fontSize": num(10)}}]}


def slicer_obj(dropdown=False):
    o = {"header": [{"properties": {"show": LB(False)}}],
         "items": [{"properties": {"fontSize": num(11)}}]}
    if dropdown:
        o["data"] = [{"properties": {"mode": L("Dropdown")}}]
    return o


def title_box(text):
    return {"title": [{"properties": {"show": LB(True), "text": L(text)}}]}


def chart(vtype, roles, title=None, sort=None, objects=None):
    q = {"queryState": {role: {"projections": [proj(f) for f in fields]} for role, fields in roles.items()}}
    if sort:
        q["sortDefinition"] = {"sort": [{"field": sort[0][0], "direction": sort[1]}]}
    v = {"visualType": vtype, "query": q, "drillFilterOtherVisuals": True}
    if title:
        v["visualContainerObjects"] = title_box(title)
    if objects:
        v["objects"] = objects
    return v


def text(paragraphs):
    """paragraphs: list of (text, bold, size_pt)."""
    paras = [{"textRuns": [{"value": t, "textStyle": ({"fontWeight": "bold"} if b else {}) | {"fontSize": f"{s}pt"}}]}
             for t, b, s in paragraphs]
    return {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paras}}]},
            "drillFilterOtherVisuals": True}


def min_trains_filter(minimum=2000):
    return [{"name": "f_min_run", "field": meas("Trains Run")[0], "type": "Advanced",
             "filter": {"Version": 2, "From": [{"Name": "m", "Entity": "_Measures", "Type": 0}],
                        "Where": [{"Condition": {"Comparison": {"ComparisonKind": 2, "Left": {"Measure": {
                            "Expression": {"SourceRef": {"Source": "m"}}, "Property": "Trains Run"}},
                            "Right": {"Literal": {"Value": f"{minimum}L"}}}}}]}}]


def heat_format():
    f = meas("Late Arrival Rate")
    rule = {"FillRule": {"Input": f[0], "FillRule": {"linearGradient2": {
        "min": {"color": {"Literal": {"Value": "'#FFFFFF'"}}}, "max": {"color": {"Literal": {"Value": "'#C60C30'"}}},
        "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}}}}}}
    return {"values": [{"properties": {"fontSize": num(9)}},
                       {"properties": {"backColor": {"solid": {"color": {"expr": rule}}}},
                        "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": f[1]}}],
            "columnHeaders": [{"properties": {"fontSize": num(9)}}], "rowHeaders": [{"properties": {"fontSize": num(9)}}]}


def slicers_left(p, y0=64):
    specs = [("Service", col("dim_route", "service"), 100, False), ("Journey length", col("dim_route", "journey_band"), 140, False),
             ("Year", col("dim_date", "year"), 70, True), ("Axis", col("dim_route", "axis"), 240, False)]
    y = y0
    for title, f, h, dd in specs:
        p.add(20, y, 200, h, chart("slicer", {"Values": [f]}, title=title, objects=slicer_obj(dd)))
        y += h + 8


def slicers_top(p, y=56):
    specs = [("Service", col("dim_route", "service")), ("Journey length", col("dim_route", "journey_band")),
             ("Year", col("dim_date", "year")), ("Axis", col("dim_route", "axis"))]
    for i, (title, f) in enumerate(specs):
        p.add(20 + i * 315, y, 305, 76, chart("slicer", {"Values": [f]}, title=title, objects=slicer_obj(True)))


FINDINGS = [
    ("Punctuality is getting worse after a post-2021 low",
     "Late arrivals peaked at 17.8% of trains in 2018, fell to 11.3% in 2021, then rose again. January to September 2026 sits at 18.7% against 14.3% in 2025."),
    ("When a train is late, it is later than before",
     "The average delay of a late train grew from 30.7 minutes (2018) to 40.4 (2026). Trains over 60 minutes late went from 1.5% to 3.1% of runs between 2021 and 2026."),
    ("Summer is the weak season",
     "July has the highest late rate of the year (18.5%) and the most severe delays, against 12.2% in March."),
    ("Cross-country routes are the least reliable",
     "Routes that do not touch Paris are late 19.5% of the time, against 14.0% for routes with a Paris terminal."),
    ("Cancellations spike with disruption",
     "April 2020 shows 53.6% of planned trains cancelled, April 2021 37.5% and April 2018 32.7%."),
    ("No single cause dominates",
     "External causes (22%), traffic management (21%), infrastructure (21%) and rolling stock (19%) each explain about a fifth of late trains."),
]


def write_visuals(base):
    # ---- Home
    p = Page("home")
    p.add(20, 6, 1240, 58, text([("How punctual is the TGV, and where does it break down?", True, 22)]))
    p.add(20, 62, 1240, 34, text([("SNCF open data: monthly TGV regularity by route, January 2018 to September 2026", False, 13)]))
    for i, m in enumerate(["Trains Planned", "Late Arrival Rate", "Over 60 Rate", "Avg Delay of Late Trains (min)"]):
        p.add(20 + i * 312, 105, 296, 100, chart("card", {"Values": [meas(m)]}, title=m, objects=CARD_OBJ))
    for i, (head, body) in enumerate(FINDINGS):
        x, y = 20 + (i % 3) * 416, 220 + (i // 3) * 150
        p.add(x, y, 400, 140, text([(head, True, 14), (body, False, 12)]))
    p.add(20, 525, 1240, 185, text([
        ("Method and limits", True, 13),
        ("Source: SNCF Voyageurs, Regularite mensuelle TGV par liaisons, Open Database Licence (ODbL).", False, 11),
        ("Rates are ratios of sums: late arrivals divided by trains run, cancellations divided by trains planned.", False, 11),
        ("A TGV serving several routes is counted on each of them, so these are route-level movements, not the official SNCF network regularity.", False, 11),
        ("Cause shares are an estimate. The axis is derived from the Paris terminal of each route.", False, 11)]))

    # ---- Overview
    p = Page("overview")
    p.add(20, 2, 900, 58, text([("TGV Punctuality | Overview", True, 20)]))
    slicers_left(p)
    for i, m in enumerate(["Trains Planned", "Cancellation Rate", "Late Arrival Rate", "Over 60 Rate", "Avg Delay of Late Trains (min)"]):
        p.add(240 + i * 206, 60, 196, 100, chart("card", {"Values": [meas(m)]}, title=m, objects=CARD_OBJ))
    p.add(240, 170, 510, 260, chart("lineChart", {"Category": [col("dim_date", "month")], "Y": [meas("Late Arrival Rate")]},
                                    title="Late-arrival rate"))
    p.add(760, 170, 500, 260, chart("clusteredColumnChart", {"Category": [col("dim_date", "month")], "Y": [meas("Cancellation Rate")]},
                                    title="Cancellation rate"))
    p.add(240, 440, 510, 270, chart("clusteredBarChart", {"Category": [col("dim_route", "axis")], "Y": [meas("Late Arrival Rate")]},
                                    title="Late-arrival rate by axis", sort=(meas("Late Arrival Rate"), "Descending")))
    p.add(760, 440, 500, 270, chart("donutChart", {"Category": [col("Outcome", "Outcome")], "Y": [meas("Outcome Trains")]},
                                    title="What happened to every planned train", objects=DONUT_OBJ))

    # ---- Routes & Causes
    p = Page("routes")
    p.add(20, 0, 900, 58, text([("TGV Punctuality | Routes & Causes", True, 20)]))
    slicers_top(p)
    p.add(20, 140, 1240, 235, chart("tableEx", {"Values": [col("dim_route", "route"), meas("Trains Run"), meas("Late Arrival Rate"),
                                                           meas("Over 60 Rate"), meas("Total Delay Hours")]},
                                    title="Routes ranked (2,000+ trains run)", sort=(meas("Late Arrival Rate"), "Descending")),
          filters=min_trains_filter())
    p.add(20, 385, 330, 325, chart("clusteredBarChart", {"Category": [col("fact_delay_cause", "cause")], "Y": [meas("Cause Share")]},
                                   title="Estimated causes of late trains", sort=(meas("Cause Share"), "Descending")))
    p.add(360, 385, 640, 325, chart("pivotTable", {"Rows": [col("dim_date", "year")], "Columns": [col("dim_date", "month_name")],
                                                   "Values": [meas("Late Arrival Rate")]},
                                    title="Seasonality: late-arrival rate", objects=heat_format()))
    p.add(1010, 385, 250, 325, chart("clusteredBarChart", {"Category": [col("dim_route", "journey_band")],
                                                          "Y": [meas("Over 30 Rate"), meas("Over 60 Rate")]},
                                    title="Severe delays by journey length"))


def main():
    write(OUT / f"{NAME}.pbip", json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                             "settings": {"enableAutoRecovery": True}}, indent=2))
    write(SM / "definition.pbism", json.dumps({"version": "4.0", "settings": {}}, indent=2))
    write(SM / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    write(SM / "definition" / "model.tmdl",
          "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n"
          "\tsourceQueryCulture: en-US\n\n" + "".join(f"ref table {t}\n" for t in TABLES + ["_Measures", "Outcome"]))
    for t in TABLES:
        write(SM / "definition" / "tables" / f"{t}.tmdl", table_tmdl(t))
    write(SM / "definition" / "tables" / "Outcome.tmdl", outcome_table())
    mt, names = measures_table()
    write(SM / "definition" / "tables" / "_Measures.tmdl", mt)
    rels = [("fact_route_month.route_id", "dim_route.route_id"), ("fact_route_month.month", "dim_date.month"),
            ("fact_delay_cause.route_id", "dim_route.route_id"), ("fact_delay_cause.month", "dim_date.month")]
    write(SM / "definition" / "relationships.tmdl",
          "\n".join(f"relationship {guid()}\n\tfromColumn: {a}\n\ttoColumn: {b}\n" for a, b in rels))

    # report: three empty pages
    base = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
    write(RP / "definition.pbir", json.dumps({"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2))
    write(RP / "definition" / "version.json", json.dumps({"$schema": f"{base}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}, indent=2))
    write(RP / "definition" / "report.json", json.dumps({"$schema": f"{base}/report/1.0.0/schema.json",
          "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"},
                              "customTheme": {"name": "sncf_theme.json", "reportVersionAtImport": "5.61", "type": "RegisteredResources"}},
          "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                                "items": [{"name": "sncf_theme.json", "path": "sncf_theme.json", "type": "CustomTheme"}]}],
          "layoutOptimization": "None"}, indent=2))
    write(RP / "StaticResources" / "RegisteredResources" / "sncf_theme.json", (OUT / "sncf_theme.json").read_text(encoding="utf-8"))
    pages = [("home", "Home"), ("overview", "Overview"), ("routes", "Routes & Causes")]
    write(RP / "definition" / "pages" / "pages.json", json.dumps({"$schema": f"{base}/pagesMetadata/1.0.0/schema.json",
          "pageOrder": [p for p, _ in pages], "activePageName": "overview"}, indent=2))
    for pid, title in pages:
        write(RP / "definition" / "pages" / pid / "page.json", json.dumps({"$schema": f"{base}/page/1.0.0/schema.json",
              "name": pid, "displayName": title, "displayOption": "FitToPage", "height": 720, "width": 1280}, indent=2))
    write_visuals(base)
    write(OUT / ".gitignore", ".pbi/\n*.pbix.tmp\n")
    print(f"wrote {OUT / (NAME + '.pbip')} with {len(names)} measures:")
    for n in names:
        print("  -", n)


if __name__ == "__main__":
    main()
