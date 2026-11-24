#!/usr/bin/env python3
"""Add photos and building facts to the sites in raw.json -> enrich.json.

Runs between fetch_raw.py and process.py. Three free, keyless sources:

  * Wikidata (for the ~340 sites OSM links to a Wikidata item): the item's
    image (P18), inception (P571) and architect (P84).
  * Wikimedia Commons: a 640px thumbnail of that image plus the photographer
    and license, so every photo on the map carries its credit.
  * NYC Building Footprints (Socrata 5zhs-2jue): the year the city's records
    give for when the building went up, plus its tax lot (BBL). Matched by the
    building number (BIN) OSM carries for most mapped buildings, and by
    point-in-footprint for sites mapped as a single point.

If a source fails, the previous enrich.json is kept for that source rather
than wiped, so a flaky API can't strip the photos off the map.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw.json")
OUT = os.path.join(HERE, "enrich.json")
UA = {"User-Agent": "nyc-religion-map/1.0 (github.com/joshgreenman1973/nyc-religion-map)"}
FOOTPRINTS = "https://data.cityofnewyork.us/resource/5zhs-2jue.json"


def get_json(url, params=None, tries=4):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.loads(r.read())
        except Exception as e:                       # noqa: BLE001 - retry anything
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url[:120]}: {last}")


def key(el):
    return f"{el['type']}/{el['id']}"


def strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def year_of(wd_time):
    m = re.match(r"[+-](\d{4})", wd_time or "")
    return int(m.group(1)) if m else None


# ---------- Wikidata + Commons ----------

def wikidata(qids):
    items = {}
    for i in range(0, len(qids), 50):
        r = get_json("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
            "props": "claims", "format": "json"})
        for q, ent in r.get("entities", {}).items():
            c = ent.get("claims", {})

            def vals(p):
                return [s["mainsnak"].get("datavalue", {}).get("value")
                        for s in c.get(p, []) if s.get("rank") != "deprecated"]
            items[q] = {
                "image": next((v for v in vals("P18") if v), None),
                "inception": next((year_of(v.get("time")) for v in vals("P571") if v), None),
                "architects": [v["id"] for v in vals("P84") if v],
            }
    # architect names
    arch = sorted({a for it in items.values() for a in it["architects"]})
    names = {}
    for i in range(0, len(arch), 50):
        r = get_json("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": "|".join(arch[i:i + 50]),
            "props": "labels", "languages": "en", "format": "json"})
        for q, ent in r.get("entities", {}).items():
            lab = ent.get("labels", {}).get("en", {}).get("value")
            if lab:
                names[q] = lab
    for it in items.values():
        it["architects"] = [names[a] for a in it["architects"] if a in names]
    return items


def commons(files):
    out = {}
    for i in range(0, len(files), 50):
        chunk = files[i:i + 50]
        r = get_json("https://commons.wikimedia.org/w/api.php", {
            "action": "query", "format": "json", "prop": "imageinfo",
            "titles": "|".join("File:" + f for f in chunk),
            "iiprop": "url|extmetadata", "iiurlwidth": 640,
            "iiextmetadatafilter": "Artist|LicenseShortName|DateTimeOriginal"})
        # The API normalizes titles (underscores, capitalisation); map back.
        norm = {n["to"]: n["from"] for n in r["query"].get("normalized", [])}
        for page in r["query"]["pages"].values():
            info = (page.get("imageinfo") or [None])[0]
            if not info or not info.get("thumburl"):
                continue
            title = norm.get(page["title"], page["title"])
            meta = info.get("extmetadata", {})
            taken = strip_html(meta.get("DateTimeOriginal", {}).get("value"))
            out[title[len("File:"):]] = {
                "thumb": info["thumburl"],
                "page": info["descriptionurl"],
                "artist": strip_html(meta.get("Artist", {}).get("value"))[:80],
                "license": strip_html(meta.get("LicenseShortName", {}).get("value")),
                "year": int(taken[:4]) if re.match(r"\d{4}", taken) else None,
            }
    return out


# ---------- city building footprints ----------

def fp_row(x):
    bbl = str(x.get("mappluto_bbl") or x.get("base_bbl") or "").split(".")[0]
    yr = x.get("construction_year")
    yr = int(float(yr)) if yr else None
    # 0 and far-future values are placeholders in the footprint file.
    if yr and not (1600 <= yr <= 2026):
        yr = None
    return {"bin": x.get("bin"), "bbl": bbl if len(bbl) == 10 else None, "built": yr}


def footprints_by_bin(bins):
    out = {}
    bins = sorted(bins)
    for i in range(0, len(bins), 100):
        chunk = bins[i:i + 100]
        rows = get_json(FOOTPRINTS, {
            "$select": "bin,base_bbl,mappluto_bbl,construction_year",
            "$where": "bin in(%s)" % ",".join(f"'{b}'" for b in chunk),
            "$limit": 1000})
        for x in rows:
            out[x["bin"]] = fp_row(x)
    return out


def footprints_by_point(points):
    """points: {key: (lat, lon)} -> {key: row}. Batched OR of intersects()."""
    out = {}
    items = list(points.items())
    for i in range(0, len(items), 25):
        chunk = items[i:i + 25]
        where = " OR ".join(
            f"intersects(the_geom, 'POINT ({lon} {lat})')" for _, (lat, lon) in chunk)
        rows = get_json(FOOTPRINTS, {
            "$select": "bin,base_bbl,mappluto_bbl,construction_year,the_geom",
            "$where": where, "$limit": 1000})
        # Assign each returned footprint back to whichever point falls inside it.
        for k, (lat, lon) in chunk:
            for x in rows:
                if inside(lon, lat, x.get("the_geom")):
                    out[k] = fp_row(x)
                    break
    return out


def inside(x, y, geom):
    if not geom:
        return False
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        ring = poly[0]
        hit = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
        if hit:
            return True
    return False


def main():
    els = json.load(open(RAW))["elements"]
    prev = json.load(open(OUT)) if os.path.exists(OUT) else {}
    out = {"wikidata": prev.get("wikidata", {}), "commons": prev.get("commons", {}),
           "footprints": prev.get("footprints", {})}

    qids = sorted({e["tags"]["wikidata"] for e in els if e.get("tags", {}).get("wikidata")})
    try:
        wd = wikidata(qids)
        files = sorted({it["image"] for it in wd.values() if it["image"]})
        cm = commons(files)
        out["wikidata"], out["commons"] = wd, cm
        print(f"wikidata: {len(wd)} items, {len(files)} with an image, "
              f"{len(cm)} thumbnails resolved")
    except Exception as e:                           # noqa: BLE001
        print(f"WARNING wikidata/commons failed, keeping previous: {e}", file=sys.stderr)

    try:
        bins = {}
        pts = {}
        for e in els:
            t = e.get("tags", {})
            b = (t.get("nycdoitt:bin") or "").split(";")[0].strip()
            if b.isdigit() and not b.endswith("000000"):   # x000000 = placeholder BIN
                bins[key(e)] = b
            else:
                c = e.get("center") or e
                if "lat" in c:
                    pts[key(e)] = (c["lat"], c["lon"])
        by_bin = footprints_by_bin(set(bins.values()))
        fp = {k: by_bin[b] for k, b in bins.items() if b in by_bin}
        # Any BIN the footprint file didn't know falls back to the point lookup.
        for k in bins:
            if k not in fp:
                e = next(x for x in els if key(x) == k)
                c = e.get("center") or e
                pts[k] = (c["lat"], c["lon"])
        fp.update(footprints_by_point(pts))
        out["footprints"] = fp
        print(f"footprints: {len(fp)} of {len(els)} sites matched to a building "
              f"({sum(1 for v in fp.values() if v['built'])} with a year built)")
    except Exception as e:                           # noqa: BLE001
        print(f"WARNING footprints failed, keeping previous: {e}", file=sys.stderr)

    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(out, fh, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, OUT)
    print("wrote enrich.json")


if __name__ == "__main__":
    main()
