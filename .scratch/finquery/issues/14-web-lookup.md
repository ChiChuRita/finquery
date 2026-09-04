# 14: Self-directed web lookup

**What to build:** When web lookup is switched on in Settings, the categorizer and the chat agent can look up a merchant they do not recognize. Only a scrubbed merchant token leaves the machine. The agent runs a search loop of its own, deciding how many searches and page reads it needs within a budget, and stops when it has enough. Every request is written to an outbound log before it is sent and is visible in Settings. Results are cached per merchant token so a merchant leaves at most once per profile. Off by default.

**Blocked by:** 07 Categorization at import with Question card

**Status:** ready-for-agent

- [ ] Merchant token scrubber removing amounts, dates, IBANs, card and reference numbers, personal names
- [ ] Search through a keyless multi-backend library with explicit backend fallback and error handling on rate limits; page fetch with size and time limits
- [ ] Self-directed loop with a search and fetch budget; the agent's stop decision is its own
- [ ] Outbound log written before each request; Settings shows the switch and the log
- [ ] `lookup_merchant` tool for the chat agent and a lookup stage in the categorizer when enabled
- [ ] Sources rendered in the transcript with the AI Elements sources component
- [ ] HTTP-seam tests with a stubbed search client: switch off means no outbound call, token scrubbing, cache hit avoids a second request, log entry precedes the request
- [ ] Browser verification of an unknown merchant lookup
