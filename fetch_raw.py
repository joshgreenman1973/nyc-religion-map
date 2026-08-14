#!/usr/bin/env python3
"""Pull raw.json from the Overpass API using overpass-query.txt.

process.py turns raw.json into the data.json the map loads. Keeping the fetch
in its own script means the query that produced the data is the query in the
repo, not something typed into a browser once and forgotten.

Fails loudly: an Overpass error, an unparseable response, an empty result, or
an element count that has collapsed against the committed raw.json all abort
before raw.json is touched.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw.json")
QUERY_FILE = os.path.join(HERE, "overpass-query.txt")

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

MIN_RETAINED_SHARE = 0.70


def fetch(query):
    last = None
    for endpoint in ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=urllib.parse.urlencode({"data": query}).encode(),
                    headers={"User-Agent": "nyc-religion-map/1.0 (github.com/joshgreenman1973)"},
                )
                with urllib.request.urlopen(req, timeout=300) as r:
                    payload = json.loads(r.read())
                if "elements" not in payload:
                    raise RuntimeError(f"no elements key: {str(payload)[:200]}")
                return payload
            except Exception as e:                  # noqa: BLE001 - retry anything
                last = e
                wait = 10 * (attempt + 1)
                print(f"  {endpoint} attempt {attempt + 1} failed ({e}); "
                      f"retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"Overpass unavailable: {last}")


def main():
    query = open(QUERY_FILE).read()
    print("querying Overpass...")
    payload = fetch(query)
    n = len(payload["elements"])
    if not n:
        raise SystemExit("FAILED: Overpass returned 0 elements — refusing to overwrite")

    if os.path.exists(RAW):
        was = len(json.load(open(RAW)).get("elements", []))
        if was and n < was * MIN_RETAINED_SHARE:
            raise SystemExit(
                f"FAILED: {n} elements vs {was} committed "
                f"(< {MIN_RETAINED_SHARE:.0%}) — looks like a bad response, not real churn")

    tmp = RAW + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, RAW)
    print(f"wrote raw.json: {n} elements")


if __name__ == "__main__":
    main()
