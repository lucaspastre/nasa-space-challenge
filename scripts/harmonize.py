import pandas as pd, numpy as np

RES, PAR, TAU = 0.25, 8, 50          # célula 0.25°, região-pai 2°, força do shrinkage
OV_START = pd.Timestamp("2018-04-01")  # início NOAA-20
OV_END   = pd.Timestamp("2025-12-01")  # fim do MODIS que temos

pts = pd.read_parquet("data/proc/points.parquet")
pts["gx"] = np.floor(pts.longitude / RES).astype(int)
pts["gy"] = np.floor(pts.latitude / RES).astype(int)
pts["month"] = pts.date.dt.to_period("M").dt.to_timestamp()

cells = (pts.groupby(["gx", "gy", "month", "sensor"]).size()
            .unstack("sensor", fill_value=0).reset_index())
cells["px"], cells["py"] = cells.gx // PAR, cells.gy // PAR

def fit_k(ov):
    k_dom = ov.viirs.sum() / ov.modis.sum()
    p = ov.groupby(["px", "py"])[["viirs", "modis"]].sum()
    p["kp"] = (p.viirs + TAU * k_dom) / (p.modis + TAU)
    c = ov.groupby(["gx", "gy", "px", "py"])[["viirs", "modis"]].sum().reset_index()
    c = c.join(p.kp, on=["px", "py"])
    c["k"] = (c.viirs + TAU * c.kp) / (c.modis + TAU)
    return k_dom, p[["kp"]], c[["gx", "gy", "k"]]

def apply_k(df, k_dom, p, c):
    df = df.merge(c, on=["gx", "gy"], how="left").join(p, on=["px", "py"])
    df["k"] = df.k.fillna(df.kp).fillna(k_dom)
    return df.drop(columns="kp")

# ---- harmonização final (calibra com toda a sobreposição)
ov = cells[(cells.month >= OV_START) & (cells.month <= OV_END)]
k_dom, p, c = fit_k(ov)
h = apply_k(cells, k_dom, p, c)
h["H"] = np.where(h.month >= OV_START, h.viirs, h.k * h.modis)
h.to_parquet("data/proc/harmonized.parquet")
print(f"k_dom = {k_dom:.2f}")

# ---- validação: calibra 2018-04..2021, testa 2022..2025
split = pd.Timestamp("2022-01-01")
k_tr, p_tr, c_tr = fit_k(ov[ov.month < split])
v = apply_k(ov[ov.month >= split], k_tr, p_tr, c_tr)
v["pred_hier"] = v.k * v.modis
v["pred_global"] = k_tr * v.modis

def mape(real, pred):
    return (abs(real - pred) / real).mean() * 100

m = v.groupby("month")[["viirs", "modis", "pred_global", "pred_hier"]].sum()
r = v.groupby(["px", "py", "month"])[["viirs", "modis", "pred_global", "pred_hier"]].sum()
r = r[r.viirs >= 50]                 # ignora região-mês com quase nada
for col, nome in [("modis", "MODIS bruto"), ("pred_global", "k único"), ("pred_hier", "k hierárquico")]:
    print(f"{nome:15s} MAPE Brasil {mape(m.viirs, m[col]):5.1f}%   MAPE regiões 2° {mape(r.viirs, r[col]):5.1f}%")
m.reset_index().to_parquet("data/proc/validation.parquet")