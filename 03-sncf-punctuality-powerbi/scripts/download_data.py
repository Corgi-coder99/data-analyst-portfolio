"""Download the SNCF monthly TGV regularity dataset (open data, ODbL).

Source : https://ressources.data.sncf.com/explore/dataset/regularite-mensuelle-tgv-aqst/
Output : data/tgv_raw.csv

Usage (from project root): python scripts/download_data.py
"""
import urllib.request
from pathlib import Path

URL = ("https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/"
       "regularite-mensuelle-tgv-aqst/exports/csv?delimiter=%3B")
OUT = Path(__file__).resolve().parent.parent / "data" / "tgv_raw.csv"

if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    urllib.request.urlretrieve(URL, OUT)
    print(f"saved {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")
