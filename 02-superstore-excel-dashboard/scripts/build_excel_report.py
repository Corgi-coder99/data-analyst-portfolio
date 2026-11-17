"""Build Superstore_Dashboard.xlsx end to end.

Stage 1 (any OS, pandas + xlsxwriter): clean the CSV and write the workbook skeleton:
    Raw_Data (Excel Table + helper columns), Pivot_Analysis, Dashboard (KPI cards, hidden gridlines).
Stage 2 (Windows + desktop Excel + pywin32): drive Excel through COM to add what no Python
    library can write: real PivotTables, Pivot Charts, Slicers and a Timeline, all linked.

Usage (from project root):
    pip install pandas xlsxwriter pywin32
    python scripts/build_excel_report.py            # both stages
    python scripts/build_excel_report.py --stage1   # skeleton only (no Excel needed)
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import xlsxwriter

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "SampleSuperstore.csv"
XLSX = ROOT / "output" / "Superstore_Dashboard.xlsx"
PNG = ROOT / "assets" / "dashboard_preview.png"

NAVY, TEAL, LIGHT = "#1F3A5F", "#2A9D8F", "#F1F5F9"
# The only missing postal code in the source: Burlington, Vermont.
POSTAL_FIX = {("Burlington", "Vermont"): "05401"}

HELPERS = [  # (header, formula, number format)
    ("Order Year", "=YEAR([@[Order Date]])", "0"),
    ("Order Month", '=TEXT([@[Order Date]],"mmm")', None),
    ("Order YearMonth", '=TEXT([@[Order Date]],"yyyy-mm")', None),
    ("Profit Margin", "=[@Profit]/[@Sales]", "0.0%"),
    ("Delivery Days", "=[@[Ship Date]]-[@[Order Date]]", "0"),
]


# --------------------------------------------------------------------------- stage 1
def clean() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    raw_rows = len(df)
    df = df.dropna(subset=["Order ID", "Order Date"]).copy()          # fully blank records
    df = df.drop_duplicates()
    assert df["Row ID"].is_unique, "Row ID should be unique after cleaning"
    df["Row ID"] = df["Row ID"].astype(int)
    df["Order Date"] = pd.to_datetime(df["Order Date"], format="%m/%d/%Y")
    df["Ship Date"] = pd.to_datetime(df["Ship Date"], format="%m/%d/%Y")
    df["Quantity"] = df["Quantity"].astype(int)
    df["Postal Code"] = df["Postal Code"].map(lambda v: "" if pd.isna(v) else str(int(v)).zfill(5))
    for (city, state), code in POSTAL_FIX.items():
        df.loc[(df.City == city) & (df.State == state) & (df["Postal Code"] == ""), "Postal Code"] = code
    for col in ["Segment", "Region", "Category", "Sub-Category", "Ship Mode"]:
        df[col] = df[col].str.strip()
    df = df.sort_values(["Order Date", "Row ID"]).reset_index(drop=True)
    print(f"cleaned: {raw_rows} -> {len(df)} rows; missing postal codes left: {(df['Postal Code'] == '').sum()}")
    return df


def build_skeleton(df: pd.DataFrame) -> None:
    XLSX.parent.mkdir(exist_ok=True)
    wb = xlsxwriter.Workbook(str(XLSX), {"default_date_format": "yyyy-mm-dd"})
    f_date = wb.add_format({"num_format": "yyyy-mm-dd"})
    f_money = wb.add_format({"num_format": "$#,##0.00"})
    f_pct = wb.add_format({"num_format": "0%"})

    # ---- Raw_Data ------------------------------------------------------------------
    ws = wb.add_worksheet("Raw_Data")
    fmt = {"Order Date": f_date, "Ship Date": f_date, "Sales": f_money, "Profit": f_money, "Discount": f_pct}
    cols = [{"header": c, **({"format": fmt[c]} if c in fmt else {})} for c in df.columns]
    for h, formula, nf in HELPERS:
        cols.append({"header": h, "formula": formula, **({"format": wb.add_format({"num_format": nf})} if nf else {})})
    data = df.astype(object).where(df.notna(), None).values.tolist()
    ws.add_table(0, 0, len(df), len(cols) - 1, {"name": "tblSales", "style": "Table Style Medium 2",
                                                 "columns": cols, "data": data})
    ws.freeze_panes(1, 0)
    widths = {"Order ID": 16, "Order Date": 12, "Ship Date": 12, "Customer Name": 20, "City": 16, "State": 16,
              "Product Name": 40, "Product ID": 17, "Sub-Category": 13, "Order YearMonth": 16}
    for i, c in enumerate(df.columns.tolist() + [h for h, _, _ in HELPERS]):
        ws.set_column(i, i, widths.get(c, 12))

    # ---- Pivot_Analysis (pivots are added in stage 2) -----------------------------
    wp = wb.add_worksheet("Pivot_Analysis")
    wp.hide_gridlines(2)
    h = wb.add_format({"bold": True, "font_size": 12, "font_color": NAVY})
    wp.write("A1", "Pivot Analysis - all PivotTables below share one cache and respond to the Dashboard slicers",
             wb.add_format({"bold": True, "font_size": 14, "font_color": NAVY}))
    for cell, text in {"A2": "1. KPI overview", "A6": "2. Monthly trend", "E6": "3. Category performance",
                       "J6": "4. Region x Segment", "J16": "5. Segment split",
                       "P6": "6. Profit by Sub-Category (chart source)"}.items():
        wp.write(cell, text, h)
    for col, w in {"A": 16, "B": 13, "C": 13, "D": 3, "E": 22, "F": 13, "G": 13, "H": 14, "I": 3,
                   "J": 16, "K": 13, "L": 13, "M": 13, "N": 13, "O": 3, "P": 18, "Q": 14}.items():
        wp.set_column(f"{col}:{col}", w)

    # ---- Dashboard -------------------------------------------------------------------
    wd = wb.add_worksheet("Dashboard")
    wd.hide_gridlines(2)
    wd.set_column("A:A", 24)
    wd.set_column("B:B", 2)
    wd.set_column("C:N", 12)
    wd.set_row(0, 26); wd.set_row(1, 18); wd.set_row(2, 8); wd.set_row(3, 18)
    wd.set_row(4, 24); wd.set_row(5, 24)
    wd.merge_range("A1:N1", "SUPERSTORE SALES DASHBOARD",
                   wb.add_format({"bold": True, "font_size": 20, "font_color": "white", "bg_color": NAVY,
                                  "valign": "vcenter", "indent": 1}))
    wd.merge_range("A2:N2", "Use the slicers and the timeline to filter every KPI and chart",
                   wb.add_format({"font_size": 10, "font_color": "#DCE6F2", "bg_color": NAVY, "indent": 1}))
    cards = [("C", "E", "TOTAL SALES", "Total Sales", "$#,##0"), ("F", "H", "TOTAL PROFIT", "Total Profit", "$#,##0"),
             ("I", "K", "UNITS SOLD", "Units Sold", "#,##0"), ("L", "N", "PROFIT MARGIN", "Margin %", "0.0%")]
    for c1, c2, label, field, nf in cards:
        wd.merge_range(f"{c1}4:{c2}4", label, wb.add_format({"bold": True, "font_size": 9, "font_color": "#64748B",
                                                             "bg_color": LIGHT, "align": "center", "valign": "vcenter",
                                                             "top": 2, "top_color": TEAL}))
        wd.merge_range(f"{c1}5:{c2}6", 0, wb.add_format({"bold": True, "font_size": 22, "font_color": NAVY,
                                                         "bg_color": LIGHT, "align": "center", "valign": "vcenter",
                                                         "num_format": nf}))
        wd.write_formula(f"{c1}5", f'=GETPIVOTDATA("{field}",Pivot_Analysis!$A$3)',
                         wb.add_format({"bold": True, "font_size": 22, "font_color": NAVY, "bg_color": LIGHT,
                                        "align": "center", "valign": "vcenter", "num_format": nf}), 0)
    wd.write("A4", "FILTERS", wb.add_format({"bold": True, "font_size": 9, "font_color": "#64748B"}))
    wb.get_worksheet_by_name("Dashboard").activate()
    wb.close()
    print("stage 1 done:", XLSX)


# --------------------------------------------------------------------------- stage 2
def add_pivots() -> None:
    import pythoncom
    import win32com.client as win32

    E = pythoncom.Empty
    XL_SUM, XL_AVG = -4157, -4106
    xl = win32.DispatchEx("Excel.Application")
    xl.Visible = True          # visible so CopyPicture / window features behave
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Open(str(XLSX))
        wp, wd = wb.Worksheets("Pivot_Analysis"), wb.Worksheets("Dashboard")
        pc = wb.PivotCaches().Create(1, "tblSales")
        pts = []

        def make(dest, name, rows=(), cols=(), values=()):
            pt = pc.CreatePivotTable(wp.Range(dest), name)
            for i, f in enumerate(rows):
                pf = pt.PivotFields(f); pf.Orientation = 1; pf.Position = i + 1
            for i, f in enumerate(cols):
                pf = pt.PivotFields(f); pf.Orientation = 2; pf.Position = i + 1
            for field, caption, fn, nf in values:
                df_ = pt.AddDataField(pt.PivotFields(field), caption, fn)
                df_.NumberFormat = nf
            pt.TableStyle2 = "PivotStyleMedium2"
            pts.append(pt)
            return pt

        # P1 - KPIs (incl. a calculated field: ratio of sums, not mean of ratios)
        p1 = make("A3", "pvtKPI", values=[("Sales", "Total Sales", XL_SUM, "$#,##0"),
                                           ("Profit", "Total Profit", XL_SUM, "$#,##0"),
                                           ("Quantity", "Units Sold", XL_SUM, "#,##0")])
        p1.CalculatedFields().Add("Profit Margin Calc", "=Profit/Sales", True)
        p1.AddDataField(p1.PivotFields("Profit Margin Calc"), "Margin %", XL_SUM).NumberFormat = "0.0%"
        # P2 - monthly trend (YearMonth sorts correctly as text)
        make("A7", "pvtMonthly", rows=["Order YearMonth"],
             values=[("Sales", "Total Sales", XL_SUM, "$#,##0"), ("Profit", "Total Profit", XL_SUM, "$#,##0")])
        # P3 - category / sub-category table
        make("E7", "pvtCategory", rows=["Category", "Sub-Category"],
             values=[("Sales", "Total Sales", XL_SUM, "$#,##0"), ("Profit", "Total Profit", XL_SUM, "$#,##0"),
                     ("Discount", "Avg Discount", XL_AVG, "0.0%")])
        # P4 - region x segment, P5 - segment split
        make("J7", "pvtRegionSegment", rows=["Region"], cols=["Segment"],
             values=[("Sales", "Total Sales", XL_SUM, "$#,##0")])
        make("J17", "pvtSegment", rows=["Segment"], values=[("Sales", "Total Sales", XL_SUM, "$#,##0")])
        # P6 - profit by sub-category, sorted (chart source)
        p6 = make("P7", "pvtSubCatProfit", rows=["Sub-Category"], values=[("Profit", "Total Profit", XL_SUM, "$#,##0")])
        p6.PivotFields("Sub-Category").AutoSort(1, "Total Profit")

        # Pivot charts on the dashboard
        def chart(pt, kind, anchor, left_off, top_off, w, h, title, legend=True):
            cell = wd.Range(anchor)
            shp = wd.Shapes.AddChart2(-1, kind, cell.Left + left_off, cell.Top + top_off, w, h)
            ch = shp.Chart
            ch.SetSourceData(pt.TableRange1)
            ch.HasTitle = True
            ch.ChartTitle.Text = title
            ch.ChartTitle.Font.Size = 12
            ch.ChartTitle.Font.Bold = True
            ch.HasLegend = legend
            try:
                ch.ShowAllFieldButtons = False
            except Exception:
                pass
            return ch

        c1 = chart(pts[1], 4, "C8", 0, 0, 470, 235, "Monthly Sales & Profit")
        c1.Axes(1).TickLabelSpacing = 6
        c1.Axes(2).TickLabels.NumberFormat = "$#,##0,K"
        c2 = chart(p6, 57, "C8", 480, 0, 285, 235, "Profit by Sub-Category", legend=False)
        c2.Axes(1).TickLabelSpacing = 1
        c2.Axes(1).TickLabels.Font.Size = 8
        chart(pts[3], 58, "C8", 0, 245, 380, 225, "Sales by Region and Segment")
        chart(pts[4], -4120, "C8", 390, 245, 375, 225, "Sales by Segment")

        # Slicers (Region / Segment / Category) + Timeline (Order Date), connected to EVERY pivot
        def connect(sc):
            for pt in pts[1:]:
                sc.PivotTables.AddPivotTable(pt)

        top = wd.Range("A4").Top + 16
        for field, h in [("Region", 118), ("Segment", 98), ("Category", 98)]:
            sc = wb.SlicerCaches.Add2(pts[0], field, E, E)
            connect(sc)
            sc.Slicers.Add(wd, E, f"sl{field}", field, top, 6, 132, h)
            top += h + 8
        tl = wb.SlicerCaches.Add2(pts[0], "Order Date", E, 2)
        connect(tl)
        tl_top = wd.Range("C8").Top + 480
        tl.Slicers.Add(wd, E, "tlOrderDate", "Order Date", tl_top, wd.Range("C8").Left, 765, 95)

        for pt in pts:
            pt.PivotCache().RefreshOnFileOpen = True
        xl.CalculateFull()
        wd.Activate()
        wd.Range("A1").Select()
        wb.Save()
        print("stage 2 done: pivots, charts, slicers added")

        # preview image
        try:
            from PIL import ImageGrab
            wd.Range("A1:N47").CopyPicture(1, 2)
            img = ImageGrab.grabclipboard()
            if img is not None:
                PNG.parent.mkdir(exist_ok=True)
                img.save(PNG)
                print("preview saved:", PNG)
        except Exception as exc:  # preview is a nice-to-have
            print("preview skipped:", exc)
        wb.Close(SaveChanges=True)
    finally:
        xl.Quit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage1", action="store_true", help="only build the skeleton (no Excel needed)")
    args = ap.parse_args()
    build_skeleton(clean())
    if not args.stage1:
        if sys.platform != "win32":
            sys.exit("Stage 2 needs Windows + desktop Excel. Re-run with --stage1 or on Windows.")
        add_pivots()
