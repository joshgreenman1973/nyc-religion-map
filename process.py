#!/usr/bin/env python3
"""Turn raw.json (Overpass) + enrich.json (photos, building dates) into data.json."""
import json, re

raw = json.load(open("raw.json"))

# Map religion + denomination -> (group, label)
# group is the top-level filter category; label is shown on the marker.

CHRISTIAN_GROUPS = {
    "catholic": "Catholic",
    "roman_catholic": "Catholic",
    "greek_catholic": "Catholic",
    "baptist": "Baptist",
    "southern_baptist": "Baptist",
    "lutheran": "Lutheran",
    "evangelical_lutheran": "Lutheran",
    "methodist": "Methodist",
    "united_methodist": "Methodist",
    "african_methodist_episcopal": "Methodist",
    "african_methodist_episcopal_zion": "Methodist",
    "free_methodist": "Methodist",
    "pentecostal": "Pentecostal",
    "assemblies_of_god": "Pentecostal",
    "church_of_god": "Pentecostal",
    "presbyterian": "Presbyterian",
    "episcopal": "Episcopal/Anglican",
    "anglican": "Episcopal/Anglican",
    "orthodox": "Orthodox Christian",
    "greek_orthodox": "Orthodox Christian",
    "russian_orthodox": "Orthodox Christian",
    "romanian_orthodox": "Orthodox Christian",
    "serbian_orthodox": "Orthodox Christian",
    "ukrainian_orthodox": "Orthodox Christian",
    "coptic_orthodox": "Orthodox Christian",
    "ethiopian_orthodox": "Orthodox Christian",
    "antiochian_orthodox": "Orthodox Christian",
    "syriac_orthodox": "Orthodox Christian",
    "jehovahs_witness": "Jehovah's Witness",
    "seventh_day_adventist": "Adventist",
    "adventist": "Adventist",
    "mormon": "Latter-day Saints",
    "latter_day_saints": "Latter-day Saints",
    "reformed": "Reformed",
    "dutch_reformed": "Reformed",
    "christian_reformed": "Reformed",
    "christ_scientist": "Christian Scientist",
    "quaker": "Quaker",
    "mennonite": "Mennonite",
    "moravian": "Moravian",
    "salvation_army": "Salvation Army",
    "nondenominational": "Nondenominational",
    "non-denominational": "Nondenominational",
    "evangelical": "Evangelical (other)",
    "protestant": "Protestant (other)",
    "non_denomination": "Nondenominational",
    "united_reformed": "Reformed",
    "congregational": "Congregational/UCC",
    "united_church_of_christ": "Congregational/UCC",
    "armenian_apostolic": "Orthodox Christian",
    "armenian_orthodox": "Orthodox Christian",
    "albanian_orthodox": "Orthodox Christian",
    "bulgarian_orthodox": "Orthodox Christian",
    "church_of_christ": "Other Christian",
    "nazarene": "Other Christian",
    "apostolic": "Other Christian",
    "fire_baptized_holiness": "Other Christian",
    "philadelphian": "Other Christian",
    "spiritist": "Other Christian",
    "universal_church_of_the_kingdom_of_god": "Other Christian",
    "anabaptist": "Other Christian",
    "old_catholic": "Other Christian",
    "new_apostolic": "Other Christian",
}

JEWISH_GROUPS = {
    "orthodox": "Jewish — Orthodox",
    "hasidic": "Jewish — Orthodox",
    "modern_orthodox": "Jewish — Orthodox",
    "conservative": "Jewish — Conservative",
    "reform": "Jewish — Reform",
    "reconstructionist": "Jewish — Reconstructionist",
    "sephardic": "Jewish — Sephardic",
    "humanistic": "Jewish — Other",
    "jewish": "Jewish — Unspecified",
}

MUSLIM_GROUPS = {
    "sunni": "Muslim — Sunni",
    "shia": "Muslim — Shia",
    "ahmadiyya": "Muslim — Ahmadiyya",
    "ibadi": "Muslim — Other",
    "nation_of_islam": "Muslim — Nation of Islam",
}


def classify(tags):
    r = (tags.get("religion") or "").lower().strip()
    d = (tags.get("denomination") or "").lower().strip().replace(" ", "_")
    # Tagging slips seen in the NYC data: a Catholic religion value, a
    # mosque tagged "mue", and sites with a denomination but no religion.
    if r in ("roman_catholic", "catholic"):
        r, d = "christian", d or "catholic"
    if r == "mue":
        r = "muslim"
    if r in ("", "none", "(none)"):
        if d == "jewish":
            r, d = "jewish", ""
        elif d in CHRISTIAN_GROUPS:
            r = "christian"
        else:
            return ("Unknown / unspecified", "Unspecified")
    if r == "christian":
        if d in CHRISTIAN_GROUPS:
            return ("Christian", CHRISTIAN_GROUPS[d])
        # try second-token (e.g., "catholic_charismatic")
        for key in CHRISTIAN_GROUPS:
            if d.startswith(key):
                return ("Christian", CHRISTIAN_GROUPS[key])
        return ("Christian", "Christian — unspecified")
    if r == "jewish":
        if d in JEWISH_GROUPS:
            return ("Jewish", JEWISH_GROUPS[d])
        return ("Jewish", "Jewish — Unspecified")
    if r == "muslim":
        if d in MUSLIM_GROUPS:
            return ("Muslim", MUSLIM_GROUPS[d])
        return ("Muslim", "Muslim — Unspecified")
    if r == "buddhist":
        return ("Buddhist", f"Buddhist{' — '+d.title() if d else ''}")
    if r == "hindu":
        return ("Hindu", "Hindu")
    if r == "sikh":
        return ("Sikh", "Sikh")
    if r == "unitarian_universalist":
        return ("Other", "Unitarian Universalist")
    if r == "taoist":
        return ("Other", "Taoist")
    if r == "shinto":
        return ("Other", "Shinto")
    if r == "ethical":
        return ("Other", "Ethical Culture")
    if r == "jain":
        return ("Other", "Jain")
    return ("Other", r.replace("_", " ").title())


# ---------- enrichment (photos, building dates) ----------

import os
from collections import Counter

ENRICH = json.load(open("enrich.json")) if os.path.exists("enrich.json") else {}
WD = ENRICH.get("wikidata", {})
CM = ENRICH.get("commons", {})
FP = ENRICH.get("footprints", {})

# The city's footprint file piles estimated construction dates onto a few
# years: citywide, 1930 has ~112,000 buildings and 1931 and 1935 ~37,000
# each, against 1,000-5,000 for the years around them. Round decades are
# estimates too (St. Patrick's Cathedral, finished 1878, is listed as 1910).
# Only the specific years are kept.


def plausible_year(y):
    return bool(y) and y % 10 != 0 and y not in (1931, 1935)


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def wiki_link(tags):
    w = tags.get("wikipedia") or ""
    if ":" in w:
        lang, title = w.split(":", 1)
        return f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
    return ""


def record(el):
    tags = el.get("tags", {})
    if "center" in el:
        lat, lon = el["center"]["lat"], el["center"]["lon"]
    elif "lat" in el:
        lat, lon = el["lat"], el["lon"]
    else:
        return None
    k = f"{el['type']}/{el['id']}"
    group, label = classify(tags)
    p = {
        "id": el["type"][0] + str(el["id"]),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "n": clean(tags.get("name") or tags.get("name:en")),
        "g": group,
        "d": label,
        "a": " ".join(x for x in (clean(tags.get("addr:housenumber")),
                                  clean(tags.get("addr:street"))) if x),
        "w": tags.get("website") or tags.get("contact:website") or "",
    }
    wp = wiki_link(tags)
    if wp:
        p["wp"] = wp
    fp = FP.get(k)
    if fp and plausible_year(fp.get("built")):
        p["b"] = fp["built"]
    wd = WD.get(tags.get("wikidata") or "")
    if wd:
        if wd.get("inception"):
            p["f"] = wd["inception"]
        if wd.get("architects"):
            p["ar"] = wd["architects"][:3]
        ph = CM.get(wd.get("image") or "")
        if ph:
            p["ph"] = {"t": ph["thumb"], "p": ph["page"],
                       "a": ph["artist"], "l": ph["license"]}
    return p, tags, k, fp


# ---------- build, then drop duplicate mappings of the same site ----------

rows = [r for r in (record(el) for el in raw["elements"]) if r]


def richness(r):
    p, tags, _, _ = r
    return ("ph" in p, bool(tags.get("wikidata")), len(tags))


def near(a, b, m=80):
    return (abs(a["lat"] - b["lat"]) * 111000 < m and
            abs(a["lon"] - b["lon"]) * 84000 < m)


# OSM sometimes maps one congregation twice: a point and a building outline,
# or two outlines for a church and its parish house. Same name, and either the
# same city building (BIN) or within 80 metres, counts as one site; the copy
# with a photo or more tags is kept.
rows.sort(key=richness, reverse=True)
kept, dropped = [], []
for r in rows:
    p, tags, k, fp = r
    dup = False
    if p["n"]:
        for q in kept:
            if q[0]["n"].lower() == p["n"].lower() and (
                    (fp and q[3] and fp.get("bin") and fp.get("bin") == q[3].get("bin"))
                    or near(p, q[0])):
                dup = True
                break
    (dropped if dup else kept).append(r)

points = [r[0] for r in kept]
points.sort(key=lambda p: (p["lat"], p["lon"]))

group_counts = Counter(p["g"] for p in points)
denom_counts = Counter(p["d"] for p in points)

print("Total:", len(points), f"({len(dropped)} duplicate mappings dropped)")
print("Groups:", group_counts.most_common())
print("With photo:", sum(1 for p in points if "ph" in p),
      "| with year built:", sum(1 for p in points if "b" in p))
print("Top denominations:")
for x in denom_counts.most_common(40):
    print(" ", x)

import datetime
with open("data.json", "w") as f:
    json.dump({"points": points,
               "groups": group_counts.most_common(),
               "denoms": denom_counts.most_common(),
               "duplicates_dropped": len(dropped),
               "footprint_matches": sum(1 for r in kept if r[3]),
               # Dates the data itself: the map and the methodology page both
               # read this, so a stalled refresh shows an old date rather than
               # a hand-typed one that stays current-looking forever.
               # Use the OSM snapshot time Overpass reports, so rebuilding
               # data.json locally doesn't make old data look freshly pulled.
               "generated": ((raw.get("osm3s") or {}).get("timestamp_osm_base") or
                             datetime.datetime.now(datetime.timezone.utc).isoformat())[:10]}, f,
              separators=(",", ":"), ensure_ascii=False)
print("Size KB:", round(os.path.getsize("data.json") / 1024, 1))
