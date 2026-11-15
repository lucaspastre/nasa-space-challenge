import pandas as pd, glob
import json, shapely
from shapely.geometry import shape

BR = shape(json.load(open("data/raw/brasil.geojson"))["features"][0]["geometry"])
shapely.prepare(BR)

def read(f):
    df = pd.read_csv(f, usecols=lambda c: c in COLS)
    if "api" in f:
        df = df[shapely.contains_xy(BR, df.longitude.values, df.latitude.values)]
    return df


COLS = {"latitude", "longitude", "acq_date", "confidence", "frp", "daynight", "type"}

def load(pattern, sensor):
    files = sorted(glob.glob(pattern))
    print(sensor, len(files), "arquivos")
    df = pd.concat(read(f) for f in files)
    if sensor == "modis":
        df = df[df.confidence >= 30]
    else:
        df = df[df.confidence.astype(str).str[0].isin(["n", "h"])]
    if "type" in df:
        df = df[df.type.fillna(0) == 0]     # 0 = vegetação
    df["date"] = pd.to_datetime(df.acq_date)
    df["sensor"] = sensor
    return df[["latitude", "longitude", "date", "frp", "daynight", "sensor"]]

pts = pd.concat([load("data/raw/modis*.csv", "modis"),
                 load("data/raw/viirs*.csv", "viirs")], ignore_index=True)
pts.to_parquet("data/proc/points.parquet")

print(pts.groupby([pts.date.dt.year, "sensor"]).size().unstack())