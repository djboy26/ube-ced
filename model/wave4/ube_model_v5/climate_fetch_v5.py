"""
climate_fetch_v5.py - re-download the monthly climate the dwelling model uses (network needed)

PVGIS v5.2 (European Commission JRC) seriescalc: hourly 2005-2020, ERA5 2 m temperature and SARAH-2
irradiation on vertical planes facing S (aspect 0), E (-90), W (90) and N (180), at Copenhagen, Odense
and Aalborg; aggregated here to monthly mean temperature and monthly irradiation (kWh/m2).
Retrieved 19 September 2026. Output: _dsdata/pvgis_monthly_2005_2020.csv
"""
import json, urllib.request, csv, sys, os
LOCS = {"copenhagen": (55.68, 12.57), "odense": (55.40, 10.39), "aalborg": (57.05, 9.92)}
ASP = {"S": 0, "E": -90, "W": 90, "N": 180}
URL = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc?lat={lat}&lon={lon}&angle=90&aspect={asp}&startyear=2005&endyear=2020&outputformat=json"
rows = []
for loc, (lat, lon) in LOCS.items():
    agg = {}
    for o, asp in ASP.items():
        u = URL.format(lat=lat, lon=lon, asp=asp)
        d = json.loads(urllib.request.urlopen(u, timeout=300).read())
        for h in d["outputs"]["hourly"]:
            y, m = int(h["time"][:4]), int(h["time"][4:6])
            a = agg.setdefault((y, m), {"n": 0, "T": 0.0})
            a[o] = a.get(o, 0.0) + h["G(i)"] / 1000.0
            if o == "S":
                a["n"] += 1; a["T"] += h["T2m"]
        print(loc, o, len(d["outputs"]["hourly"]), file=sys.stderr)
    for (y, m), a in sorted(agg.items()):
        rows.append([loc, y, m, round(a["T"] / a["n"], 3), round(a["S"], 3), round(a["E"], 3), round(a["W"], 3), round(a["N"], 3)])
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_dsdata", "pvgis_monthly_2005_2020.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["location", "year", "month", "T2m_mean_C", "G_vert_S_kWh_m2", "G_vert_E_kWh_m2", "G_vert_W_kWh_m2", "G_vert_N_kWh_m2"]); w.writerows(rows)
