import os, pandas as pd, datetime as dt, requests, io

KEY = os.environ["FIRMS_KEY"]
BBOX = "-74,-34,-34,6"

def fetch(src, d):
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/{src}/{BBOX}/5/{d}"
    r = requests.get(url, timeout=60)
    if r.status_code != 200 or not r.text.startswith("latitude"):
        print("   falhou", src, d, r.status_code, r.text[:150])
        return None
    return pd.read_csv(io.StringIO(r.text))

d, end = dt.date(2026, 1, 1), dt.date.today()
dfs = []
while d <= end:
    for src in ["VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT"]:
        df = fetch(src, d)
        if df is not None and len(df):
            dfs.append(df)
            print(d, src, len(df))
            break
    d += dt.timedelta(days=5)

pd.concat(dfs).to_csv("data/raw/viirs_api_2026.csv", index=False)
print("salvo")