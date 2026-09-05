"""The last check between the model's words and the reader.

Two things a small model does to an answer, both caught here rather than asked for in a prompt:

- **A figure it computed itself.** ADR 0004 says every number comes from an executed query. The
  9B review of 2026-09-05 broke that in eleven of 46 turns, once reporting net savings of
  83,64 EUR where the nine rows it had just been given sum to 429,40 EUR. So every euro amount
  in the answer is compared against the figures this turn's tools returned (and the ones the
  user wrote themselves), and a figure that is in neither is replaced, in place, by a sentence
  the server writes quoting what the query did return.
- **A stray token from another script.** The same review's long turns produced "Gesamτή",
  "kündigen,iven" and the Russian word "править" inside German sentences. A word carrying
  letters of a script this app never answers in is dropped, unless the whole text is written in
  one (which would mean the leak is the answer, not a token in it).

Both are used twice: on the stream, so the reader never sees the figure, and on the text that is
stored, so a reload does not bring it back (`finquery.api.chat`).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from finquery.formats import eur

CENT_TOLERANCE = 1
"""How far a prose figure may sit from the figure a query returned. One cent covers rounding."""

QUOTED_LINES = 3
"""How many of the turn's figure lines the replacement sentence quotes."""

# A euro amount as either language writes it: 1.234,56 EUR, 1,234.56 EUR, 12 EUR, 12,50 €,
# EUR 12,50. A bare number is not money: "23 transactions" is a count, not a figure to check.
_NUMBER = r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_CURRENCY = r"EUR|€|Euros?"
MONEY = re.compile(
    rf"(?:(?P<before>{_CURRENCY})\s*(?P<after_amount>{_NUMBER})|(?P<amount>{_NUMBER})\s*(?:{_CURRENCY}))",
    re.IGNORECASE,
)
_DECIMAL = re.compile(rf"(?<![\d.,])(?:{_NUMBER})(?!\d)")
_NUMERIC = re.compile(r"^-?\d+(?:[.,]\d+)?$")

_ENDS = ".!?"
_GERMAN_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.$")


def sentences(text: str) -> list[str]:
    """The text cut into sentences, each with its terminator and its line break.

    Written out rather than a regex because the thing being looked for is a figure: a full stop
    between two digits is a thousands separator (1.234,56) and ends nothing, and the one closing
    a German date ("01.07. bis 30.09.") ends nothing either.
    """
    parts: list[str] = []
    start = 0
    for index, character in enumerate(text):
        if character == "\n":
            parts.append(text[start : index + 1])
            start = index + 1
        elif character in _ENDS:
            before = text[index - 1] if index else ""
            after = text[index + 1] if index + 1 < len(text) else ""
            if before.isdigit() and (after.isdigit() or _GERMAN_DATE.search(text[max(0, index - 5) : index + 1])):
                continue
            parts.append(text[start : index + 1])
            start = index + 1
    if start < len(text):
        parts.append(text[start:])
    return parts


def to_cents(written: str) -> int | None:
    """`1.234,56` and `1,234.56` are both 123456 cents. Returns None when it is not a number.

    The last separator with one or two digits behind it is the decimal point; a separator with
    three digits behind it groups thousands, whichever character it is.
    """
    text = written.strip().replace(" ", "")
    if not text:
        return None
    negative = text.startswith("-")
    text = text.lstrip("+-")
    if not text or not text[0].isdigit():
        return None
    decimals = ""
    if (cut := max(text.rfind("."), text.rfind(","))) != -1 and len(text) - cut - 1 in (1, 2):
        decimals, text = text[cut + 1 :], text[:cut]
    digits = re.sub(r"[.,]", "", text)
    if not digits.isdigit() or (decimals and not decimals.isdigit()):
        return None
    cents = int(digits) * 100 + int(decimals.ljust(2, "0") or 0)
    return -cents if negative else cents


def money_in(text: str) -> list[tuple[str, int]]:
    """Every euro amount in a piece of prose, as it is written and in cents."""
    found: list[tuple[str, int]] = []
    for match in MONEY.finditer(text):
        written = match.group("amount") or match.group("after_amount")
        if written and (cents := to_cents(written)) is not None:
            found.append((written, cents))
    return found


def names_an_amount(text: str) -> list[int]:
    """The amounts the user's own message names, in cents.

    Looser than `money_in`, because a person writes "that Edeka booking was 42,30" without the
    currency. Used by `apply_simple_edit` to tell an amount the user asked for from one the
    model filled the field with.
    """
    amounts = [cents for _, cents in money_in(text)]
    for match in _DECIMAL.finditer(text):
        if (cents := to_cents(match.group())) is not None and cents not in amounts:
            amounts.append(cents)
    return amounts


@dataclass
class Figures:
    """The figures this turn is allowed to state: what its tools returned, and what the user wrote.

    Permissive on purpose. Every number a tool result carries counts as a figure the answer may
    quote, because rewriting a sentence that was right is worse than letting a figure through
    that happens to equal a row count. What it catches is the figure that is in none of them:
    the sum, the difference or the estimate the model worked out in its own words.
    """

    cents: set[int] = field(default_factory=set)
    lines: list[str] = field(default_factory=list)
    """The `figures` lines of the turn's query and chart results, for the replacement sentence."""

    def add_result(self, output: Any) -> None:
        """Take in one tool result, whatever shape it has."""
        if isinstance(output, dict):
            for key, value in output.items():
                if key == "figures" and isinstance(value, list):
                    self.lines.extend(str(line) for line in value)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self.cents.add(round(value * 100))
                    if key.endswith("_cents"):
                        self.cents.add(int(value))
                else:
                    self.add_result(value)
        elif isinstance(output, (list, tuple)):
            for item in output:
                self.add_result(item)
        elif isinstance(output, str):
            # A preview row carries its amount as "-7.90"; a tool that answers in a sentence
            # carries it as "120.00 EUR". Both are figures the answer may quote.
            if _NUMERIC.match(output.strip()) and (cents := to_cents(output)) is not None:
                self.cents.add(cents)
            else:
                self.cents.update(cents for _, cents in money_in(output))

    def add_message(self, text: str) -> None:
        """The amounts the user wrote themselves. Quoting those back is not inventing them."""
        self.cents.update(names_an_amount(text))

    def allows(self, cents: int) -> bool:
        return any(abs(cents - known) <= CENT_TOLERANCE for known in self.cents)

    def quote(self) -> str:
        """The figures the turn really produced, as one readable list."""
        if self.lines:
            return "; ".join(self.lines[:QUOTED_LINES])
        return "; ".join(f"{eur(cents)} EUR" for cents in sorted(self.cents)[:QUOTED_LINES])


REPLACED = {
    "en": (
        "One figure here did not come from any query of this turn, so it was removed. "
        "The query returned: {figures}."
    ),
    "de": (
        "Eine Zahl an dieser Stelle stammte aus keiner Abfrage dieser Antwort und wurde "
        "entfernt. Die Abfrage ergab: {figures}."
    ),
}
DROPPED = {
    "en": "Another figure here did not come from a query either, so it was removed.",
    "de": "Auch diese Zahl stammte aus keiner Abfrage und wurde entfernt.",
}
NOTHING_QUERIED = {
    "en": "One figure here did not come from any query of this turn, so it was removed.",
    "de": "Eine Zahl an dieser Stelle stammte aus keiner Abfrage dieser Antwort und wurde entfernt.",
}


@dataclass
class AnswerCheck:
    """One turn's answer, judged sentence by sentence as it is written.

    Live it is fed the tool results as they come back and the text deltas after them; on the way
    into the database the same object is built from the stored turn, so both agree.
    """

    figures: Figures = field(default_factory=Figures)
    language: str = "en"
    rewritten: int = 0
    _quoted: bool = False

    def clean(self, text: str) -> str:
        """The text with every unsupported figure replaced and every stray token dropped."""
        if not text:
            return text
        cleaned = strip_foreign_tokens(text)
        if not self.figures.lines:
            # No query has produced a figure in this conversation, so there is nothing to judge
            # a figure against: the prompt's rule (no figure without a query) is the only guard,
            # and a number here may as easily be the user's own or a date as an invention.
            return cleaned
        return "".join(self._sentence(part) for part in sentences(cleaned))

    def _sentence(self, sentence: str) -> str:
        amounts = money_in(sentence)
        if not amounts or all(self.figures.allows(cents) for _, cents in amounts):
            return sentence
        self.rewritten += 1
        replacement = self._replacement()
        # The sentence's own line break is kept, so a bullet list stays a bullet list.
        tail = sentence[len(sentence.rstrip("\n")) :]
        return f"{replacement}{tail or ' '}"

    def _replacement(self) -> str:
        language = "de" if self.language == "de" else "en"
        if self._quoted:
            return DROPPED[language]
        self._quoted = True
        if not self.figures.lines and not self.figures.cents:
            return NOTHING_QUERIED[language]
        return REPLACED[language].format(figures=self.figures.quote())


# --------------------------------------------------------------------------- foreign tokens

_SCRIPTS = ("LATIN", "COMMON", "DIGIT")
"""The scripts a German or English answer is written in. A letter of any other is a leak."""

MAX_FOREIGN_SHARE = 0.3
"""Above this share of the words, the other script is the text and not a stray token in it."""


def _is_foreign(word: str) -> bool:
    for character in word:
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        if not name.startswith("LATIN"):
            return True
    return False


def strip_foreign_tokens(text: str) -> str:
    """Drop single words carrying letters of another script.

    Gemma and Qwen both slip a token of another language into a long German answer ("Gesamτή",
    "править"). A whole word is dropped rather than the character, because half a word is worse
    than none, and nothing is dropped when the text is mostly written that way: that is a model
    answering in another language, which is a different problem.
    """
    # Odd positions are the whitespace between the words, so the line breaks of a list survive.
    parts = re.split(r"(\s+)", text)
    words = [index for index in range(0, len(parts), 2) if parts[index]]
    foreign = {index for index in words if _is_foreign(parts[index])}
    if not foreign or len(foreign) > max(1, len(words) * MAX_FOREIGN_SHARE):
        return text
    kept: list[str] = []
    drop_next_space = False
    for index, part in enumerate(parts):
        if index in foreign:
            # One space goes with the word, so no double space is left behind: the one in front
            # of it, or the one after it when the word opened a line.
            if kept and kept[-1] == " ":
                kept.pop()
            else:
                drop_next_space = True
            continue
        if drop_next_space and part == " ":
            drop_next_space = False
            continue
        drop_next_space = False
        kept.append(part)
    return "".join(kept)
