"""Onboarding: the state a profile is in, and the two turns the server seeds for it.

A profile that has not started onboarding opens it instead of an empty chat. The state lives on
the profile (`onboarding_state`) next to the two preferences the flow collects,
`answer_language` and `default_model_slot`, and is read and written through
`GET`/`PATCH /api/settings` like `web_lookup_enabled` already is.

Nothing here calls a model. The welcome turn is written from what the profile actually holds,
counted in code, which is the same rule the seeded review conversation follows: a number in a
turn nobody generated is a number nobody invented. Its three suggestions travel as the
`data-followups` part every answer already uses, so the existing suggestion chips render them.
"""

from datetime import date
from pathlib import Path
from typing import Literal

OnboardingState = Literal["not_started", "done", "skipped"]
AnswerLanguage = Literal["follow", "de", "en"]

SAMPLE_CSV = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic" / "sparkasse-2025.csv"
"""The shipped synthetic year, imported through the chat path by "Load the sample year"."""

SAMPLE_PROMPT = "Import this."
SAMPLE_TITLE = "The sample year"

WELCOME_TITLE = {"de": "Willkommen", "en": "Welcome"}


def _german_date(iso: str | None) -> str:
    if not iso:
        return ""
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


def welcome_text(
    language: str,
    *,
    profile_name: str,
    transaction_count: int,
    first_booked_on: str | None,
    last_booked_on: str | None,
    accounts: tuple[str, ...],
) -> str:
    """The welcome turn's one paragraph: what this profile holds, and what to do with it."""
    german = language == "de"
    if transaction_count == 0:
        if german:
            return (
                f"Willkommen bei FinQuery, {profile_name}. In diesem Profil ist noch nichts importiert. "
                "Zieh einen CSV-Export, einen Kontoauszug als PDF oder das Foto einer Rechnung in das Feld "
                "unten, dann lese ich die Datei, frage nach, wo ich unsicher bin, und importiere sie."
            )
        return (
            f"Welcome to FinQuery, {profile_name}. Nothing is imported in this profile yet. "
            "Drop a CSV export, a statement PDF or a photo of a bill into the box below and I will read "
            "it, ask about anything I am unsure of, and import it."
        )
    where = ", ".join(accounts) if accounts else ("einem Konto" if german else "one account")
    if german:
        return (
            f"Willkommen bei FinQuery, {profile_name}. Dieses Profil hat {transaction_count} Buchungen "
            f"von {_german_date(first_booked_on)} bis {_german_date(last_booked_on)} in {where}. "
            "Frag mich alles darüber: jede Zahl in meiner Antwort kommt aus einer Abfrage, die du "
            "aufklappen und lesen kannst."
        )
    return (
        f"Welcome to FinQuery, {profile_name}. This profile holds {transaction_count} bookings from "
        f"{_german_date(first_booked_on)} to {_german_date(last_booked_on)} in {where}. "
        "Ask me anything about them: every number in my answer comes from a query you can open and read."
    )


def welcome_suggestions(language: str, *, transaction_count: int, last_booked_on: str | None) -> list[str]:
    """Three things to ask first, about the data this profile really has."""
    german = language == "de"
    if transaction_count == 0:
        if german:
            return [
                "Womit kannst du mir helfen?",
                "Was brauchst du von mir, um loszulegen?",
                "Welche Dateien kannst du lesen?",
            ]
        return [
            "What can you help me with?",
            "What do you need from me to get started?",
            "Which files can you read?",
        ]
    year = (last_booked_on or "")[:4] or str(date.today().year)
    if german:
        return [
            f"Wofür habe ich {year} mein Geld ausgegeben?",
            "Welche Abos bezahle ich?",
            f"Was waren {year} meine fünf größten Ausgaben?",
        ]
    return [
        f"Where did my money go in {year}?",
        "Which subscriptions am I paying for?",
        f"What were my five biggest expenses in {year}?",
    ]


def language_rule(language: str) -> str:
    """The prompt block for a profile that fixed its answer language.

    Empty for `follow`, which is the system prompt's own rule: answer in the language of the
    newest message. When the user picked one, it has to win over that rule, so it says so.
    """
    if language == "de":
        return (
            "This profile has chosen German as its answer language. Write every answer in German, "
            "whatever language the user's message is in. This overrides the rule about answering in "
            "the language of the newest message."
        )
    if language == "en":
        return (
            "This profile has chosen English as its answer language. Write every answer in English, "
            "whatever language the user's message is in. This overrides the rule about answering in "
            "the language of the newest message."
        )
    return ""
