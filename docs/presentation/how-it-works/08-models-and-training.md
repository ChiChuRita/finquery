# Models and the fine-tuning loop

**Claim.** The shipped pair was chosen by a benchmark run with the product's own runtime, and
the two fine-tuned models are trained on data kept only by execution and scored on a frozen
held-out set from a household never seen in training.

## The benchmark

- 152 SQL questions and 73 chart requests a household really asks, in German and English, with
  gold produced by running reference SQL through the guard on the shipped synthetic year. A
  third is held out.
- Scored on figure match (to the cent), SQL validity, first attempt, and for charts shape match,
  column mapping, language and whether the frame drew it.
- Run on the HPI cluster with llama-cpp and the same Q4_K_M GGUFs and wire formats as the laptop,
  so a cluster number is a laptop number.

| model | SQL | charts | end to end (30 cases through the chat agent) | laptop tok/s |
| --- | ---: | ---: | ---: | ---: |
| Gemma 4 E4B | 66 % | 45 % | 53 % | 47 |
| Qwen3.5 9B | 70 % | 42 % | 73 % | 30 |
| Gemma 4 12B | 87 % | 81 % | 77 % | 22 |

Source: `bench/results/20260906-cluster-compare.md`, `20260906-local-tokens-per-second.md`.

The decision rule was written before the run: accuracy first, speed as a tie-breaker within
about five points, the pair must fit in about 13.5 GB. Result: Gemma 4 12B for chat and, in the
demo, every sub-agent; E4B resident as the fast seat and adapter target.

## The training loop

1. **Households.** Five new synthetic households (student, family, freelancer, pensioner, a
   couple with two accounts) with truth files, next to the shipped one.
2. **Writers.** Sixty agents write candidates: a question, the SQL, a reasoning line, and an
   independent second statement that must agree to the cent; for charts a plan, SQL and code.
   Writers never see the benchmark.
3. **Gate by execution.** Guard, database, the two statements compared, chart self-check on the
   real rows, a headless render of every chart. Drops carry reasons; wrong attempts are kept on
   purpose as repair and check-pass samples.
4. **Judges.** A second pass recomputes figures from the truth file, holds the reasoning line to
   the SQL's standard, and looks at a fifth of the pictures per shape.
5. **Frozen benchmark.** The shipped household becomes benchmark-only, so the benchmark measures
   an unseen household. The split is hashed and frozen before any training row exists.
6. **Assembly.** A sample is byte for byte the prompt the production sub-agent sends, in TRL chat
   format with completion-only loss, plus repair and check-pass rows.
7. **QLoRA.** Four adapters (query and chart, on E4B and on the 12B), rank 16 or 32, attention
   and MLP projections only, a checkpoint per epoch, a quick eval on a fixed set, the best
   checkpoint converted to GGUF with the known pitfalls checked, attached through the adapter
   registry on the fast seat.
8. **Official run.** Base against base plus adapter with the same benchmark and runtime, before
   and after per base per task. Smoke-tested end to end on an H100 (20 steps, conversion,
   attach, five cases right).

## Decisions

- No hosted models in the benchmark: the candidates are what the product can ship.
- Training equals production: a prompt drift invalidates the set, so the generator calls the
  same prompt builders.
- Reasoning judged as strictly as SQL: a rationale at partial coverage measurably loses to none.

## Say on Monday

State the training status as it is that morning from `bench/results` and `training/`. Never a
number that is not in a results file.
