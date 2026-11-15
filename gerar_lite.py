import os, pandas as pd
os.makedirs("data/proc/points", exist_ok=True)
p = pd.read_parquet("data/proc/points.parquet",
                    columns=["latitude", "longitude", "date", "frp", "daynight", "sensor"])
p = p.sort_values(["date", "sensor"])                 # ordenar melhora a compressão
for ano, g in p.groupby(p.date.dt.year):
    g.to_parquet(f"data/proc/points/{ano}.parquet", compression="zstd", index=False)
print("ok")