"""Self-directed web lookup: what an unknown merchant is, without giving anything away.

Off by default. When the profile switches it on in Settings, the chat agent gets the
`lookup_merchant` tool and the categorizer gets a stage between the merchant dictionary and the
model. Both go through `Lookups.merchant`, which scrubs the booking down to a merchant token
(`scrub`), refuses outright when that reads as a person, answers from the cache when the token
already left once, and otherwise runs the loop in `loop.py`: the fast slot decides search,
fetch or finish through a forced single tool, our code takes the step and asks again.

Every request is written to the outbound log before it is made (`store.OutboundJournal`), so
`GET /api/outbound-log` is the whole record of what ever left this machine.

- `scrub`: the merchant token, and the reason there is none
- `client`: keyless search through `ddgs`, one page fetch through `httpx`
- `loop`: the decision agent and the loop our code runs
- `store`: the outbound log and the per-token cache
- `service`: `lookups_for`, the one place the switch is read, and the three ways in
  (`merchant` for the chat tool, `merchants` for an import batch, `store` for a receipt header)
"""

from finquery.weblookup.client import Hit, HttpWebClient, Page, SearchUnavailable, WebClient
from finquery.weblookup.loop import MAX_FETCHES, MAX_SEARCHES, Decision, Outcome, lookup_prompt, run_loop
from finquery.weblookup.scrub import (
    MerchantToken,
    has_legal_form,
    looks_like_a_person,
    safe_query,
    scrub,
)
from finquery.weblookup.service import Lookup, Lookups, lookups_for
from finquery.weblookup.store import Source, recent_log, web_lookup_enabled

__all__ = [
    "MAX_FETCHES",
    "MAX_SEARCHES",
    "Decision",
    "Hit",
    "HttpWebClient",
    "Lookup",
    "Lookups",
    "MerchantToken",
    "Outcome",
    "Page",
    "SearchUnavailable",
    "Source",
    "WebClient",
    "has_legal_form",
    "lookup_prompt",
    "looks_like_a_person",
    "lookups_for",
    "recent_log",
    "run_loop",
    "safe_query",
    "scrub",
    "web_lookup_enabled",
]
