"""Generate a Power BI Project (PBIP) with the semantic model already built.

What you get: 4 tables loaded from data/processed/*.csv, the 4 relationships, a date table, hidden raw
columns, and every DAX measure from powerbi/measures.dax (single source of truth, parsed here).
The report has the three empty pages (Home, Overview, Routes & Causes): you add the visuals.

Usage (from project root):  python scripts/make_pbip.py
Then open powerbi/TGV_Punctuality.pbip in Power BI Desktop.
Needs Power BI Desktop with the "Power BI Project (.pbip) save option" preview feature enabled
(File > Options and settings > Options > Preview features).
"""
import csv
import json
import re
import uuid
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
    lines += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
              f'\t\t\t\t\tSource = Csv.Document(File.Contents(DataFolder & "\\{table}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
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


def measures_table():
    text = (OUT / "measures.dax").read_text(encoding="utf-8")
    items = split_grouped(text)
    lines = ["table _Measures", f"\tlineageTag: {guid()}", "", "\tcolumn Dummy", "\t\tdataType: int64", "\t\tisHidden",
             "\t\tformatString: 0", f"\t\tlineageTag: {guid()}", "\t\tsummarizeBy: none", "\t\tsourceColumn: [Dummy]", ""]
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
    lines += ["\tpartition _Measures = calculated", "\t\tmode: import", '\t\tsource = ROW ( "Dummy", 1 )', ""]
    return "\n".join(lines), [n for n, _ in items]


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main():
    data_folder = str(PROC)
    write(OUT / f"{NAME}.pbip", json.dumps({"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                             "settings": {"enableAutoRecovery": True}}, indent=2))
    write(SM / "definition.pbism", json.dumps({"version": "4.0", "settings": {}}, indent=2))
    write(SM / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    write(SM / "definition" / "model.tmdl",
          "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n"
          "\tsourceQueryCulture: en-US\n\n" + "".join(f"ref table {t}\n" for t in TABLES + ["_Measures"]) + "ref expression DataFolder\n")
    write(SM / "definition" / "expressions.tmdl",
          'expression DataFolder = "%s" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
          "\tlineageTag: %s\n" % (data_folder.replace("\\", "\\\\"), guid()))
    for t in TABLES:
        write(SM / "definition" / "tables" / f"{t}.tmdl", table_tmdl(t))
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
          "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"}},
          "layoutOptimization": "None"}, indent=2))
    pages = [("home", "Home"), ("overview", "Overview"), ("routes", "Routes & Causes")]
    write(RP / "definition" / "pages" / "pages.json", json.dumps({"$schema": f"{base}/pagesMetadata/1.0.0/schema.json",
          "pageOrder": [p for p, _ in pages], "activePageName": "overview"}, indent=2))
    for pid, title in pages:
        write(RP / "definition" / "pages" / pid / "page.json", json.dumps({"$schema": f"{base}/page/1.0.0/schema.json",
              "name": pid, "displayName": title, "displayOption": "FitToPage", "height": 720, "width": 1280}, indent=2))
    write(OUT / ".gitignore", ".pbi/\n*.pbix.tmp\n")
    print(f"wrote {OUT / (NAME + '.pbip')} with {len(names)} measures:")
    for n in names:
        print("  -", n)


if __name__ == "__main__":
    main()
