#!/usr/bin/env python3
"""Process Overpass raw.json -> data.js for the map."""
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
    d = (tags.get("denomination") or "").lower().strip()
    if r in ("", "none", "(none)"):
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
    if r == "jain":
        return ("Other", "Jain")
    return ("Other", r.replace("_", " ").title())


points = []
for el in raw["elements"]:
    tags = el.get("tags", {})
    if "center" in el:
        lat, lon = el["center"]["lat"], el["center"]["lon"]
    elif "lat" in el:
        lat, lon = el["lat"], el["lon"]
    else:
        continue
    group, label = classify(tags)
    name = tags.get("name") or tags.get("name:en") or ""
    addr_parts = [tags.get("addr:housenumber"), tags.get("addr:street")]
    addr = " ".join(p for p in addr_parts if p)
    points.append({
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "n": name,
        "g": group,
        "d": label,
        "a": addr,
        "w": tags.get("website") or tags.get("contact:website") or "",
    })

# Sort largest groups first for legend stability
from collections import Counter
group_counts = Counter(p["g"] for p in points)
denom_counts = Counter(p["d"] for p in points)

print("Total:", len(points))
print("Groups:", group_counts.most_common())
print("Top denominations:")
for x in denom_counts.most_common(40):
    print(" ", x)

with open("data.json", "w") as f:
    json.dump({"points": points,
               "groups": group_counts.most_common(),
               "denoms": denom_counts.most_common()}, f, separators=(",", ":"))
print("Wrote data.json:", )
import os
print("Size KB:", round(os.path.getsize("data.json")/1024, 1))
