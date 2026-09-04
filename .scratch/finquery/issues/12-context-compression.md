# 12: Context compression

**What to build:** A long conversation keeps working. A context badge in the conversation header shows tokens used against the model's context. When history passes 60 percent, turns older than the last six are distilled by the fast slot into a rolling summary that replaces them in the prompt. A divider in the transcript marks where the summary took over; the summary is readable and editable there.

**Blocked by:** 02 Profiles and conversation management

**Status:** ready-for-agent

- [ ] Token counting per slot; context stats emitted as a data part every turn
- [ ] Summarization at the threshold, stored with a summary-through marker on the conversation; per-turn prompt assembly uses summary plus recent turns
- [ ] Divider and editable summary in the transcript; edits are used on the next turn
- [ ] HTTP-seam tests with a small fake context size: summary created at the threshold, older turns no longer sent to the model, edited summary reaches the model
- [ ] Browser verification of a long chat crossing the threshold
