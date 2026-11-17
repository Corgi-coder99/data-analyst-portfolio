"""Run the 3 SQL files in order against a DuckDB database and print every result set.

Usage (from project root):  python scripts/run_all.py [--out results.txt]
Requires: pip install duckdb
"""
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
MAX_ROWS = 200
FILES = ["01_data_cleaning", "02_eda_queries", "03_tableau_views"]


def statements(sql: str):
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    for st in sql.split(";"):
        lines = [l for l in st.split("\n") if not l.strip().startswith("--")]
        st = "\n".join(lines).strip()
        if st:
            yield st


def main():
    out = open(sys.argv[sys.argv.index("--out") + 1], "w", encoding="utf-8") if "--out" in sys.argv else sys.stdout
    con = duckdb.connect(str(ROOT / "covid.duckdb"))
    import os
    os.chdir(ROOT)  # SQL uses paths relative to project root
    for name in FILES:
        sql = (ROOT / "sql" / f"{name}.sql").read_text(encoding="utf-8")
        for st in statements(sql):
            res = con.execute(st)
            if res.description and st.lstrip("( \n").upper().startswith(("SELECT", "WITH")):
                print(f"\n### {name}: {' '.join(st.split())[:80]}", file=out)
                cols = [d[0] for d in res.description]
                print(" | ".join(cols), file=out)
                rows = res.fetchall()
                for row in rows[:MAX_ROWS]:
                    print(" | ".join(str(v) for v in row), file=out)
                if len(rows) > MAX_ROWS:
                    print(f"... ({len(rows) - MAX_ROWS} more rows)", file=out)


if __name__ == "__main__":
    main()
