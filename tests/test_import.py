"""CSV import over HTTP: a preset file, an unknown bank mapped by the scripted model, junk."""

import json
from pathlib import Path

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo

from .conftest import PRIVATE, SYNTHETIC, Scripts

SPARKASSE = SYNTHETIC / "sparkasse-2025.csv"
UNKNOWN_BANK = SYNTHETIC / "unknown-bank-2025.csv"
TRADE_REPUBLIC = PRIVATE / "frames" / "tr-2025-Q1.csv"

UNKNOWN_BANK_MAPPING = {
    "date_column": "Datum",
    "debit_column": "Soll",
    "credit_column": "Haben",
    "description_column": "Buchungsinfo",
    "counterparty_column": "Empfänger/Auftraggeber",
    "date_format": "DD.MM.YYYY",
    "decimal_separator": "comma",
}


def upload(path: Path) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (path.name, path.read_bytes(), "text/csv")}


def scripted_mapping(mapping: dict[str, object], account_name: str = "Volksbank Giro") -> object:
    """A forced single tool call, the way the fast slot answers a mapping request."""
    calls: list[AgentInfo] = []

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(info)
        payload = {"mapping": mapping, "account_name": account_name, "note": "Soll is outgoing, Haben incoming."}
        return ModelResponse(parts=[ToolCallPart("propose_mapping", json.dumps(payload))])

    respond.calls = calls  # type: ignore[attr-defined]
    return respond


async def test_preset_import_of_the_synthetic_csv(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    preview = await client.post("/api/imports/preview", files=upload(SPARKASSE))
    assert preview.status_code == 200, preview.text
    body = preview.json()

    assert body["preset"] == "sparkasse"
    assert body["preset_label"] == "Sparkasse"
    assert body["mapping_source"] == "preset"
    assert body["encoding"] == "cp1252"
    assert body["delimiter"] == ";"
    assert body["account_name"] == "Sparkasse Girokonto"
    assert body["mapping"]["date_column"] == "Buchungstag"
    assert body["mapping"]["amount_column"] == "Betrag"
    assert body["mapping"]["description_column"] == "Verwendungszweck"
    assert body["mapping"]["counterparty_column"] == "Beguenstigter/Zahlungspflichtiger"
    assert body["mapping"]["decimal_separator"] == "comma"
    assert body["row_count"] == 433
    assert body["issues"] == []
    # German decimal comma and DD.MM.YYYY, read without asking the model.
    rent = next(row for row in body["rows"] if row["counterparty"] == "Hausverwaltung Bergmann GmbH")
    assert (rent["booked_on"], rent["amount_cents"]) == ("2025-01-01", -115000)
    assert scripts.resolved == []

    committed = await client.post(
        "/api/imports",
        files=upload(SPARKASSE),
        data={"profile_id": profile_id, "mapping": json.dumps(body["mapping"]), "account_name": body["account_name"]},
    )
    assert committed.status_code == 201, committed.text
    record = committed.json()
    assert (record["row_count"], record["imported_count"], record["duplicate_count"]) == (433, 433, 0)
    assert record["preset"] == "sparkasse"
    assert record["account_name"] == "Sparkasse Girokonto"

    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 5})).json()
    assert page["total"] == 433
    assert page["rows"][0]["booked_on"] == "2025-12-28"
    assert page["rows"][0]["source"] == "import"
    # Nothing is categorized at import yet: every row is Needs review until ticket 07.
    assert all(row["category"] is None for row in page["rows"])
    assert page["rows"][0]["account"] == "Sparkasse Girokonto"

    scoped = {"profile_id": profile_id}
    assert [row["id"] for row in (await client.get("/api/imports", params=scoped)).json()] == [record["id"]]
    assert [row["name"] for row in (await client.get("/api/accounts", params=scoped)).json()] == ["Sparkasse Girokonto"]


async def test_importing_the_same_file_twice_counts_duplicates(client: httpx.AsyncClient, profile_id: str) -> None:
    mapping = (await client.post("/api/imports/preview", files=upload(SPARKASSE))).json()["mapping"]
    form = {"profile_id": profile_id, "mapping": json.dumps(mapping), "account_name": "Sparkasse Girokonto"}

    first = (await client.post("/api/imports", files=upload(SPARKASSE), data=form)).json()
    second = (await client.post("/api/imports", files=upload(SPARKASSE), data=form)).json()

    assert (first["imported_count"], first["duplicate_count"]) == (433, 0)
    assert (second["imported_count"], second["duplicate_count"]) == (0, 433)
    scoped = {"profile_id": profile_id}
    assert (await client.get("/api/transactions", params=scoped)).json()["total"] == 433
    assert len((await client.get("/api/imports", params=scoped)).json()) == 2


async def test_unknown_bank_mapping_is_proposed_by_the_fast_slot_and_editable(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    respond = scripted_mapping(UNKNOWN_BANK_MAPPING)
    scripts.fast_call = respond  # type: ignore[assignment]

    body = (await client.post("/api/imports/preview", files=upload(UNKNOWN_BANK))).json()

    assert scripts.resolved == ["fast"]
    # One forced tool, no free text: that is how a schema comes back from the fast slot.
    info = respond.calls[0]  # type: ignore[attr-defined]
    assert [tool.name for tool in info.output_tools] == ["propose_mapping"]
    assert info.allow_text_output is False
    assert info.function_tools == []

    assert body["preset"] is None
    assert body["mapping_source"] == "model"
    assert body["account_name"] == "Volksbank Giro"
    assert body["note"] == "Soll is outgoing, Haben incoming."
    assert body["mapping"]["debit_column"] == "Soll"
    assert body["mapping"]["credit_column"] == "Haben"
    # Debit and credit columns are unsigned in the file; outgoing money comes back negative.
    rent = next(row for row in body["rows"] if row["counterparty"] == "Hausverwaltung Bergmann GmbH")
    assert (rent["booked_on"], rent["amount_cents"]) == ("2025-01-01", -115000)

    # The user corrects the description column in the preview before committing.
    edited = {**body["mapping"], "description_column": "Vorgangsart"}
    corrected = (
        await client.post(
            "/api/imports/preview",
            files=upload(UNKNOWN_BANK),
            data={"mapping": json.dumps(edited), "account_name": "Volksbank Giro"},
        )
    ).json()
    assert corrected["mapping_source"] == "user"
    assert corrected["rows"][0]["description"] == "Folgelastschrift"
    assert scripts.resolved == ["fast"], "an edited mapping must not call the model again"

    committed = await client.post(
        "/api/imports",
        files=upload(UNKNOWN_BANK),
        data={"profile_id": profile_id, "mapping": json.dumps(edited), "account_name": "Volksbank Giro"},
    )
    assert committed.status_code == 201
    assert committed.json()["imported_count"] == 433
    assert committed.json()["preset"] is None
    newest = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 20})).json()["rows"]
    assert {row["account"] for row in newest} == {"Volksbank Giro"}
    salary = next(row for row in newest if row["amount_cents"] > 0)
    assert (salary["booked_on"], salary["amount_cents"]) == ("2025-12-28", 285000)


async def test_malformed_uploads_are_rejected(client: httpx.AsyncClient, tmp_path: Path) -> None:
    image = SYNTHETIC / "bill-edeka-2025-03-14.png"
    assert (await client.post("/api/imports/preview", files=upload(image))).status_code == 422

    prose = tmp_path / "notes.txt"
    prose.write_text("Kontoauszug\nkeine Spalten hier\n", encoding="utf-8")
    rejected = await client.post("/api/imports/preview", files=upload(prose))
    assert rejected.status_code == 422
    assert "header" in rejected.json()["detail"]

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert (await client.post("/api/imports/preview", files=upload(empty))).status_code == 422

    # A mapping without any amount column cannot import money.
    no_amount = {"date_column": "Buchungstag", "description_column": "Verwendungszweck"}
    refused = await client.post(
        "/api/imports/preview", files=upload(SPARKASSE), data={"mapping": json.dumps(no_amount)}
    )
    assert refused.status_code == 422
    assert "amount" in refused.json()["detail"]


@pytest.mark.skipif(not TRADE_REPUBLIC.exists(), reason="the private Trade Republic export is not in this checkout")
async def test_trade_republic_preset_reads_the_real_export(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    body = (await client.post("/api/imports/preview", files=upload(TRADE_REPUBLIC))).json()

    assert body["preset"] == "traderepublic"
    assert body["mapping_source"] == "preset"
    assert body["delimiter"] == ","
    assert body["mapping"]["date_column"] == "date"
    assert body["mapping"]["amount_column"] == "amount"
    assert body["mapping"]["counterparty_column"] == "name"
    assert body["mapping"]["decimal_separator"] == "dot"
    assert body["mapping"]["date_format"] == "YYYY-MM-DD"
    assert body["issues"] == []
    assert body["row_count"] > 100
    assert scripts.resolved == [], "a recognized bank never reaches the model"

    committed = await client.post(
        "/api/imports",
        files=upload(TRADE_REPUBLIC),
        data={"profile_id": profile_id, "mapping": json.dumps(body["mapping"]), "account_name": "Trade Republic"},
    )
    assert committed.status_code == 201
    assert committed.json()["imported_count"] == body["row_count"]
