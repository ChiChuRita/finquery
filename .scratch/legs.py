"""The legs of every split, as the Transactions page lists them."""

import json
import pathlib

rows = json.loads(pathlib.Path("/tmp/finquery-30a/rows.json").read_text())["rows"]
legs = [r for r in rows if r["parent_id"]]
print(f"{len(rows)} rows listed, {len(legs)} of them legs of a split")
for leg in legs:
    print(f"  {leg['booked_on']}  {leg['amount_cents'] / 100:>8.2f}  {leg['description'][:36]:<36} {leg['category']}")
