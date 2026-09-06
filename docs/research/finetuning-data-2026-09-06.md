# How much data the query and chart adapters need

Research note, 2026-09-06 (ticket 57). Reading only: no code changed, no model run, no server
started. Every number carries its source. Numbers without a URL are measured from this repository
and name the file they came from.

## 1. What one sample is here

Both prompt builders are pure functions, so a training row is the exact text production sends
(`query_prompt` in `src/finquery/query/subagent.py`; `plan_prompt` and `code_prompt` in
`src/finquery/chart/subagent.py`). Sizes are the constant sections measured off the source at four
characters per token, plus the household paragraph.

| Prompt | Sections | Prompt tokens | Target tokens |
| --- | --- | ---: | ---: |
| `query_prompt` | instructions 121, view schema 280, rules 1,030, nine worked examples 986, profile facts ~400 | ~2,850 | ~150 (`reasoning` + `sql`) |
| `plan_prompt` | shape menu, rules 1,624, examples 1,228, profile facts ~400 | ~3,650 | ~150 |
| `code_prompt` | contract 1,344, two to four worked examples at ~315 each, rows brief ~300 | ~2,600 | ~400 (the function body) |

Three consequences. **The prompt dwarfs the target**, so loss must be masked to the completion,
which TRL does with `completion_only_loss` or `assistant_only_loss`
(https://huggingface.co/docs/trl/main/en/sft_trainer), worth 38.6 against 37.5 MMLU in QLoRA's
ablation (https://arxiv.org/pdf/2305.14314). **Nothing exceeds 4,096 tokens**, so that is the
sequence length. **An adapter is attached for a whole run**, not per call:
`bench/finquery_bench/models.py` sets `finquery_adapter` on every call, so the query adapter also
serves the retry, the rewrite and the check pass (`src/finquery/query/check.py`), and the chart
adapter serves plan, code and repair. Train all of them or risk regressing the ones you skip.

## 2. How many samples per adapter

| Evidence | Number | Source |
| --- | --- | --- |
| **Structured-output learning curve, LoRA on a 1B model**, JSON + KG + NER extraction | valid outputs 100 -> 144, 300 -> 267, 500 -> 282, 1000 -> 288: "rapid gains from 100 to 300 samples, followed by a clear plateau between 300 and 1000" | https://arxiv.org/pdf/2509.08381 |
| **TUCAN**, Bulgarian tool calling, the closest published analogue | 10,035 bilingual function-calling conversations: 2.6B +28.75 pts, 9B +8.34, 27B +0.83. Gains shrink monotonically with size | https://arxiv.org/pdf/2506.23394 |
| Qwen-7B LoRA on Spider, 5,000 train / 500 val | 36.17 % -> 45.33 % SFT -> 54.50 % with reasoning in the target | https://arxiv.org/pdf/2603.22942 |
| DTS-SQL, 7B on Spider train (8,659 examples, 200 databases) | DeepSeek-7B 85.5 % dev, 84.4 % test | https://ar5iv.labs.arxiv.org/html/2402.01117, https://arxiv.org/pdf/1809.08887 |
| ToolAlpaca, generalized tool use over 400+ APIs | 3,938 instances take 7B and 13B to GPT-3.5-comparable | https://arxiv.org/abs/2306.05301 |
| APIGen / xLAM | 60,000 verified samples: 6.7B base 40.41 % -> 85.65 % on BFCL | https://arxiv.org/pdf/2406.18518 |
| LIMA | 1,000 examples at 65B; "at least 2,000 examples improved stability" at 7B; 2k-to-32k quantity ablation plateaus | https://arxiv.org/pdf/2305.11206 |
| QLoRA | 9,209 OASST1 beat 450,000 FLAN v2; size and epochs move MMLU 0.0 to 0.5, dataset choice 1.5 to 8.0 | https://arxiv.org/pdf/2305.14314 |
| Unsloth | "a bare minimum of at least 100 rows"; "over 1,000 rows is preferable" | https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/datasets-guide |

The 1B structured-output curve is the most useful row in that table, and its elbow is **per task**,
not per dataset: three tasks, 100 to 1,000 samples each. The query adapter has eight kinds, which
behave like eight sub-tasks, over two languages. At roughly 100 to 150 per pattern that is **800 to
1,200 rows**.

The same place arrives from the other direction. Spider needs 8,659 examples because it spans 200
databases and the model must learn schema linking; FinQuery has one view, one tool and one
household paragraph, so there is no schema variety to learn. What has to be learned is the reading
of a German or English household question, which is exactly where `bench/README.md` records the
failures: 57 % figure match overall for Qwen3.5 9B, 19 % on follow-ups, 43 % on trends, 49 % at
difficulty 3. Patterned failures need coverage per pattern, not bulk.

**Recommendation: query adapter 900 rows of `write_sql` (range 700 to 1,200), plus 150 repair rows
and 150 check-pass rows, about 1,200 total. Chart adapter 500 chart requests (range 400 to 700),
yielding 500 plan rows, 500 code rows and 150 repair rows, about 1,150.** Both clear LIMA's
stability floor, both sit past the 300-per-pattern elbow, and both are small enough that every row
can be gold by execution, which is the part that actually pays.

## 3. The mix

| Dimension | Share | Why |
| --- | --- | --- |
| German / English | 50 / 50, in one adapter | MultiSpider: multilingual training beats per-language training, German +2.3 to +2.8 points and English up too, about +3.9 % overall (https://arxiv.org/pdf/2212.13492). Forty multilingual examples already shift cross-lingual behaviour (https://arxiv.org/abs/2401.01854). The benchmark is 46 % German and German is where the misspellings and Denglisch live |
| Difficulty 1 / 2 / 3 | 15 / 45 / 40 | The Spider LoRA run above used 10 / 50 / 40. Our set is 15/50/35 and Qwen scores 49 % at difficulty 3 against 78 % at 1 |
| Follow-ups with prefix | 18 to 20 % | 10.5 % of the benchmark but 19 % figure match, the worst kind by a wide margin |
| Kinds | proportional, with follow-up and trend over-weighted | Weakest after follow-up are trend 43 % and entity 54 % |
| Repairs after a failed check | 12 to 15 % of query rows, 25 to 30 % of chart code rows | Match the runtime rate: 1.21 model calls per SQL datapoint, 2.08 per chart (`bench/README.md`). Do not exceed it, or the model learns to expect a broken previous answer |
| Chart shapes | all eight, floor of 40 requests each, extra weight on doughnut (12 %) and area (0 %) | `bench/README.md` per-shape table |
| Hard cases | ~40 % at difficulty 3 | As above; LIMA shows diversity and quality carry the gain where volume does not |

**One finding changes how the `reasoning` field must be built.** A reasoning line in the target is
worth +9.17 points on identical Spider data (https://arxiv.org/pdf/2603.22942), and long rationales
gave +4.86 on challenging BIRD queries. But at 73.86 % rationale coverage the reasoning field
**lost** to plain gold SQL (63.82 against 63.95), and only at 99.02 % coverage did it win (67.41
against 66.17) (https://arxiv.org/pdf/2502.06759). So every kept row needs a validated `reasoning`
line, not just a validated statement. The execution gate cannot check prose, so the second Opus pass
must: does the reasoning name the period, the filters, the sign and the grouping the SQL actually
implements? Right SQL with hand-wavy reasoning should be dropped. APIGen adds the matching rule:
putting back samples that failed the checkers **hurts**, and hurts the smaller model more
(https://arxiv.org/pdf/2406.18518), so ticket 43's "disagreements dropped" should stay strict.

## 4. The validation size that reads a two-point difference

Base and adapter run on the same datapoints, so the test is paired (McNemar) and only items that flip
count. With `d` the share that flip and `delta` the accuracy difference, at alpha 0.05 two-sided and
80 % power:

    n = (1.96 * sqrt(d) + 0.8416 * sqrt(d - delta^2))^2 / delta^2

For delta = 0.02: **d = 0.10 needs 1,960 paired datapoints, d = 0.20 needs 3,922, d = 0.30 needs
5,884.** Unpaired is hopeless: 60 % against 62 % in two independent arms needs 9,332 per arm.
Inverting the formula gives what each candidate set can read:

| paired n | detectable at d = 0.20 | at d = 0.30 | 95 % CI half-width at p = 0.5 |
| ---: | ---: | ---: | ---: |
| 50 (SQL held-out third) | 17.3 pts | 21.2 pts | +-13.9 pts |
| 73 (whole chart set) | 14.4 pts | 17.7 pts | +-11.5 pts |
| 152 (whole SQL set) | 10.1 pts | 12.4 pts | +-7.9 pts |
| 300 | 7.2 pts | 8.8 pts | +-5.7 pts |
| 400 | 6.2 pts | 7.6 pts | +-4.9 pts |
| 1,000 | 4.0 pts | 4.8 pts | +-4.0 pts |

The n = 152 row reproduces what the repo found empirically: three runs of the same weights on the old
76-question set scored 45 %, 58 % and 50 %, and `bench/README.md` concludes "nothing under about ten
points could be read there at all".

**Two points is not buyable at any size we will build**, and we should not need it. The expected
effect is far larger: TUCAN moved a 2.6B model 28.75 points and a 9B model 8.34 on tool calling
(https://arxiv.org/pdf/2506.23394), and the Spider LoRA run moved a 7B model 18.33
(https://arxiv.org/pdf/2603.22942). An adapter that earns its place clears the ten-point floor on its
own. So hold out **400 samples per adapter**, which reads six to eight points; keep the benchmark's
held-out third as the release gate at ten points and up; and for finer resolution watch held-out
token loss, where 400 samples times ~200 target tokens is 80,000 statistical units rather than 400
binary outcomes. Report a paired bootstrap interval on every comparison. LIMA's caveat applies:
held-out perplexity rose there while generation quality still improved
(https://arxiv.org/pdf/2305.11206), so loss picks the checkpoint and the benchmark picks the release.

## 5. Starting hyperparameters

Same stack as `training/preference/train_dpo.py`: TRL, PEFT, bitsandbytes, transformers, datasets,
accelerate.

| | Gemma 4 E4B (fast slot) | Qwen3.5 9B | Gemma 4 12B |
| --- | --- | --- | --- |
| Precision | QLoRA 4-bit NF4 + double quant, or bf16 LoRA | **bf16 LoRA, not 4-bit** | bf16 LoRA |
| Rank r | 16 (second run 32) | 32 | 32 |
| alpha | 32 (2r) | 64 | 64 |
| Dropout | 0.05 | 0.05 | 0.05 |
| Target modules | leave `target_modules` unset | attention pathway only: `q_proj,k_proj,v_proj,o_proj` and the FFN of those layers | leave unset |
| Learning rate | 2e-4 | 2e-4 | 1e-4 |
| Epochs | 2 (sweep 1, 2, 3) | 2 | 2 |
| Sequence length | 4096 | 4096 | 4096 |
| Batch | 1 x grad accum 8 | 1 x 8 | 1 x 8 |
| Warmup, decay | 5 % warmup, weight decay 0.01 | same | same |
| VRAM for LoRA | 17 GB, or 10 GB in 4-bit | 22 GB bf16 | ~30 GB bf16 |

Why each value:

| Choice | Evidence |
| --- | --- |
| sequence length 4096 | Section 1: no prompt reaches it. Measure the true p100 over the generated file before the first run and raise it if a repair prompt overruns |
| these are SFT numbers, not the DPO ones | `train_dpo.py` uses r=16, alpha=32, lr 5e-6, one epoch. The low rate is correct for DPO and wrong for SFT; Unsloth gives 2e-4 for LoRA against 5e-6 for RL (https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide). Keep the two recipes separate |
| r = 16 or 32 | "We find LoRA r is unrelated to final performance if LoRA is used on all layers" (https://arxiv.org/pdf/2305.14314); a WikiSQL sweep plateaus after r=16 (r=8 53.4, r=16 59.6, r=32 60.4) (https://arxiv.org/html/2607.25583); "Choose 16 or 32" (https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide). r=16 on E4B because TUCAN found larger ranks unstable at 2.6B and tolerated only at 9B and up (https://arxiv.org/pdf/2506.23394), and E4B is 4.5B effective parameters (https://huggingface.co/google/gemma-4-E4B) |
| alpha = 2r, not a fixed 16 | alpha = 2r gives fewer intruder dimensions and better generalization (https://arxiv.org/html/2410.21228v3), which matters because the adapter is attached over prompts it was not trained for |
| lr 2e-4, two epochs | Unsloth recommends 2e-4 and "1-3 epochs", "more than 3 epochs offers diminishing returns" (https://unsloth.ai/docs/get-started/fine-tuning-llms-guide/lora-hyperparameters-guide); QLoRA used 2e-4 at 7B and 13B (https://arxiv.org/pdf/2305.14314) |
| effective batch 8 | LoRA tolerates large batches worse than full fine-tuning and rank does not fix it (https://thinkingmachines.ai/blog/lora/); TRL: "effective batch size < 32" (https://huggingface.co/docs/trl/en/lora_without_regret) |
| LoRA, never full SFT | At 64 samples full SFT drove Natural Questions accuracy to zero while LoRA held it stable at equal task accuracy (https://arxiv.org/pdf/2511.00130): forgetting we cannot afford when one adapter covers three prompts |
| Qwen3.5 bf16, attention pathway only | "It is not recommended to do QLoRA (4-bit) training on the Qwen3.5 models" (https://unsloth.ai/docs/models/qwen3.5/fine-tune). It is a 3:1 hybrid of Gated DeltaNet and gated attention (https://huggingface.co/Qwen/Qwen3.5-9B), so `q_proj` exists in one sublayer in four; adapting the recurrent backbone of a sequential hybrid cost 14.8 points on GSM8K while attention-only beat full-model adaptation with 5 to 10x fewer trainable parameters (https://arxiv.org/abs/2604.22127) |
| Gemma 4: no `target_modules="all-linear"` | PEFT raises `Target module Gemma4ClippableLinear is not supported`; 0.19.0 ships defaults scoped to the LM layers, so omitting the argument works and the explicit form does not (https://github.com/huggingface/peft/issues/3129) |
| Gemma 4: bf16, never fp16 | The audio path's mask value of -1e9 overflows fp16's 65504; a training loss of 13 to 15 on E4B is normal here, not a bug (https://unsloth.ai/docs/models/gemma-4/train) |
| No `modules_to_save` | Google's own QLoRA guide sets `["lm_head","embed_tokens"]` (https://ai.google.dev/gemma/docs/core/huggingface_text_finetune_qlora); section 9 says why that breaks the GGUF conversion |

## 6. Training time on one A100 or H100

At 900 query rows x 2 epochs x 3,000 tokens the query adapter is **5.4M training tokens**; the chart
adapter at 1,150 rows x 2 x 3,300 is **7.6M**.

Anchors: Gemma 4 31B LoRA ran 4,746 tok/s on 8x A100 and 9,559 on 8x H100, about 593 and 1,195 per
card (https://vessl.ai/en/blog/lora-finetuning-cost-a100-h100-b200); Llama-3.1-8B LoRA reached 4,962
tok/s on one RTX PRO 6000 SE
(https://www.exxactcorp.com/blog/benchmark/lora-fine-tuning-benchmark-on-nvidia-gpus); Llama-3.1 8B
QLoRA, two epochs of Alpaca at 512 tokens, took 3.2 h on an A100 40GB
(https://www.spheron.network/blog/axolotl-vs-unsloth-vs-torchtune/). Scaling by parameter count puts
E4B near 3,000 to 4,000 tok/s on an A100 and a 9B near 1,500 to 2,500.

| Adapter | Model | One A100 80GB | One H100 80GB |
| --- | --- | ---: | ---: |
| query, 5.4M tokens | E4B | 25 to 50 min | 12 to 25 min |
| query | Qwen3.5 9B | 40 to 90 min | 20 to 45 min |
| query | Gemma 4 12B | 60 to 120 min | 30 to 60 min |
| chart, 7.6M tokens | E4B | 35 to 70 min | 18 to 35 min |
| chart | Qwen3.5 9B | 55 to 130 min | 30 to 60 min |

Derived, not measured, but robust to being wrong by a factor of two: **an adapter is a lunch break on
one card, not an overnight job.** TUCAN trained its 9B on a single L4 and its 27B on one L40S
(https://arxiv.org/pdf/2506.23394), well below an A100. Treat vendor throughput claims carefully: one
study found Unsloth's headline 46,000 tok/s ran with "gradient norms of exactly zero", the corrected
figure being 11,736 (https://arxiv.org/html/2601.02609v1).

## 7. The learning curve that says whether more data helps

Train the same recipe on nested, identically stratified subsets and score each on the same held-out
400 and on the benchmark's held-out third:

    subsets: 150, 300, 500, 700, 900 rows
    fixed:   seed, epochs, rank, learning rate, validation set

Five runs per adapter is under a day per model. Read three curves: held-out token loss (fine
resolution, moves first), figure match on the 400 (six to eight points), figure match on the
benchmark third (ten points, the release gate). Expect the shape the 1B structured-output study
measured: steep to 300, elbow, flat to 1,000 (https://arxiv.org/pdf/2509.08381). If the 700-to-900
step moves loss by less than its run-to-run spread, more of the same will not help and the next 300
samples belong in the weak cells. ToolACE makes the point from the other side: at a fixed ~30,000
instances, spreading the APIs over 30 clusters rather than 6 is what moved accuracy
(https://arxiv.org/pdf/2409.00920). Diversity, not count.

## 8. Growing the benchmark from the same generation run

`bench/generate.py` already keeps a survivor only if the guard admits its statement and it returns
rows, and the 2026-09-05 review kept 107 of 190 candidates, 43 of which were "right but surplus"
(`bench/README.md`). Ticket 43's generators produce the same artifact behind a stricter gate, so
surplus survivors are benchmark-grade. Appending them raises n from 152 and 73, the only lever in
section 4 that buys real resolution.

The order of operations matters, because of `bench/finquery_bench/splits.py`. The split is a hash of
the id within a stratum of (kind or shape, hand or generated, language, difficulty), and the cut is
`int(0.3 * len(stratum) + jitter)`. Adding items **to a stratum re-cuts that stratum**, and an
existing datapoint can move from `train` to `heldout`. It has happened: ticket 52's six additions
moved `20-daily-march-en` and both German twins across (`bench/README.md`). A datapoint that moves
into `heldout` after it seeded a training sample or a worked example contaminates the held-out
number.

So: **append every kept surplus datapoint first, run `build_gold.py` then `split.py`, freeze the
files, and only then generate training data and pick worked examples.** Add a check that no training
sample's seed id is `heldout` in the frozen files, and re-run it after any later growth. The rule is
unchanged: the held-out third is never trained on, and training samples are new questions the train
split may only seed.

## 9. GGUF conversion for llama.cpp, and what breaks

The path is the one `training/preference/README.md` already names:

    python llama.cpp/convert_lora_to_gguf.py --base <base model dir> --outtype f16 <adapter dir> \
      --outfile models/adapters/query.gguf

`finquery.local.adapters` then attaches it through `llama_adapter_lora_init`. llama.cpp applies the
adapter without merging: "LoRA adapters are loaded separately and applied during inference - they are
not merged with the main model", and "the old `--lora-base` flag has been removed now that merging is
no longer performed"
(https://github.com/ggml-org/llama.cpp/blob/master/tools/completion/README.md). That removal retired
the old f16-base restriction, and a Q4_K_M base with an adapter is the worked example in Hugging
Face's walkthrough (https://huggingface.co/blog/ngxson/gguf-my-lora). The effective scale is
`adapter_scale * (alpha / r)` (https://deepwiki.com/ggml-org/llama.cpp/3.10-adapters-and-fine-tuning);
`adapters.py` passes 1.0.

Pitfalls, in the order they bite:

| # | Pitfall | Detail |
| ---: | --- | --- |
| 1 | **Qwen3.5 LoRA conversion is broken** | `NotImplementedError # can't reshape the row size trivially` in `LoraTorchTensor.reshape()` via `_reorder_v_heads()`, on Qwen3.5-9B at r = 32, open with no maintainer comment (https://github.com/ggml-org/llama.cpp/issues/21125); same class of bug as the GraniteMoe one (https://github.com/ggml-org/llama.cpp/issues/21864). It does not block E4B, the only slot sub-agents run on (ADR 0006), but it blocks any Qwen adapter |
| 2 | **Gemma 4 E4B per-layer embeddings are not in llama.cpp's forward graph** | The loader reads `gemma4.embedding_length_per_layer_input` and the `per_layer_embed` weights but never injects the residual, and it fails silently rather than crashing (https://github.com/ggml-org/llama.cpp/issues/22243). If still open against our vendored b10454, every local E4B number, adapter or not, is measured on a model missing part of its architecture. Verify against our own build before quoting a before-and-after |
| 3 | **`embed_tokens` and `lm_head` are hard-rejected** | "Embeddings is present in the adapter" (https://github.com/ggml-org/llama.cpp/blob/master/convert_lora_to_gguf.py). Worse, on a tied-embedding model the tensor can be silently skipped and the adapter converts "successfully" while never applying (https://github.com/ggml-org/llama.cpp/issues/9065) |
| 4 | **`rank_pattern`, `alpha_pattern`, `rslora`, `dora` do not round-trip** | The converter writes one global float32 `lora_alpha` and ignores the rest, so a per-module rank or `use_rslora=True` gives a wrong effective scale with no error. Keep rank and alpha uniform |
| 5 | **One unresolved crash on a quantized base** | Q8_0 plus an Unsloth adapter hit `GGML_ASSERT(tensor->view_src == nullptr)` during warmup, closed as stale (https://github.com/ggml-org/llama.cpp/issues/19436). Smoke-test the first conversion with `--dry-run` and one generation before scheduling a run |

`AdapterRegistry.attached_to` treats a missing file as a supported state and writes an audit note
(`src/finquery/local/adapters.py`), so a failed conversion degrades to base weights rather than a
broken demo. That also means a silently wrong adapter looks exactly like a working one: verify with
the benchmark, not by eye.

## 10. Recommendation

Build **900 query samples and 500 chart requests**, half German and half English in one adapter each
rather than one adapter per language, 40 percent at difficulty 3, a fifth of the query set
follow-ups with a prefix, and repair rows at the rate the runtime actually fires them, 12 to 15
percent on the query side against 25 to 30 on the chart code side, so each adapter is trained on all
three prompts it will be attached over; make the second Opus pass validate the `reasoning` line as
strictly as the execution gate validates the SQL, because a rationale field with partial coverage
measurably loses to no rationale at all and only wins near full coverage. Hold out 400 of each before
training, and append every surplus judged datapoint to the benchmark first, running `build_gold.py`
and `split.py` and freezing the files before a single training row is generated, because the split
re-cuts strata and can move a datapoint into `heldout` after you have already trained on it. Start
at r = 16 with alpha = 32 on E4B (r = 32, alpha = 64 on the larger models), dropout 0.05, learning
rate 2e-4, two epochs, sequence length 4,096, effective batch 8, `target_modules` left unset on
Gemma 4, and never save `lm_head` or `embed_tokens`; each adapter is well under two hours on one
A100, so run the 150/300/500/700/900 learning curve in the same session and let it decide whether
the next 300 samples are worth writing. Accept that a two-point difference would need 2,000 to 4,000
paired datapoints and is not buyable, but note that the comparable published fine-tunes moved small
models by 8 to 29 points, which the 152-question benchmark reads comfortably; judge checkpoints on
held-out token loss and the release on the held-out third. Before quoting any local number at all,
check llama.cpp issues 22243 and 21125, either of which would make the measurement meaningless.
