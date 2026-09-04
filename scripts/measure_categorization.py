"""Measure the categorizer against a running FinQuery: import a CSV, categorize, report.

Not part of the app. It exists so the categorizer prompt can be judged on real weights:
it prints the share of rows each stage placed, what the model was asked, what it answered with
which confidence, and the merchants left for a Question card.

    uv run python scripts/measure_categorization.py http://127.0.0.1:8058 fixtures/synthetic/sparkasse-2025.csv
"""

import json
import sys
from pathlib import Path

import httpx


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    csv_path = Path(sys.argv[2] if len(sys.argv) > 2 else "fixtures/synthetic/sparkasse-2025.csv")
    with httpx.Client(base_url=base, timeout=600) as client:
        profiles = client.get("/api/profiles").json()
        profile_id = profiles[0]["id"]
        files = {"file": (csv_path.name, csv_path.read_bytes(), "text/csv")}
        preview = client.post("/api/imports/preview", files=files).json()
        print(f"preview: {preview['row_count']} rows, mapping from {preview['mapping_source']}")
        committed = client.post(
            "/api/imports",
            files={"file": (csv_path.name, csv_path.read_bytes(), "text/csv")},
            data={
                "profile_id": profile_id,
                "mapping": json.dumps(preview["mapping"]),
                "account_name": preview["account_name"],
            },
        )
        committed.raise_for_status()
        record = committed.json()
        print(f"imported: {record['imported_count']} of {record['row_count']} ({record['duplicate_count']} duplicates)")

        report = client.post(
            f"/api/imports/{record['id']}/categorize", json={"profile_id": profile_id}
        )
        report.raise_for_status()
        body = report.json()
        rows = body["rows"] or 1
        placed = body["by_rule"] + body["by_dictionary"] + body["by_model"]
        print(
            f"\nstages over {body['rows']} rows in {body['merchants']} merchants, "
            f"{body['model_calls']} model call(s):"
        )
        print(f"  rules       {body['by_rule']:4d}  {body['by_rule'] / rows:6.1%}")
        print(f"  dictionary  {body['by_dictionary']:4d}  {body['by_dictionary'] / rows:6.1%}")
        print(f"  model       {body['by_model']:4d}  {body['by_model'] / rows:6.1%}")
        print(f"  needs review{body['needs_review']:4d}  {body['needs_review'] / rows:6.1%}")
        print(f"  categorized {placed:4d}  {placed / rows:6.1%}")
        if body["error"]:
            print(f"  error: {body['error']}")

        print("\nmerchants left for a Question card:")
        for question in body["uncertain"]:
            print(
                f"  {question['label']:<34} {question['bookings']:3d} bookings  "
                f"guess {question['guess']} ({question['confidence']})"
            )

        page = client.get(
            "/api/transactions", params={"profile_id": profile_id, "limit": 1000}
        ).json()
        seen: dict[str, tuple[str, str | None, str | None]] = {}
        for row in page["rows"]:
            seen.setdefault(row["title"] or row["description"], (row["description"], row["category"], row["subcategory"]))
        print(f"\nspot check, one row per enriched title ({len(seen)} titles):")
        for title, (description, category, subcategory) in sorted(seen.items()):
            place = f"{category} > {subcategory}" if subcategory else (category or "Needs review")
            print(f"  {title:<26} {place:<34} {description[:44]}")
        missing = [row for row in page["rows"] if not row["title"]]
        print(f"\nrows without an enriched title: {len(missing)}")


if __name__ == "__main__":
    main()
