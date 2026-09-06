# Local tokens per second, 2026-09-06

Measured on the user's laptop with llama-cpp-python 0.3.35, Metal, all layers on the GPU,
one model loaded at a time, Q4_K_M weights from `models/`. Scripts: `/tmp/fq-tps/bench.py`
(generation, greedy, 256 tokens after a 366 token prompt) and `/tmp/fq-tps/prompt.py`
(prompt processing, about 3,000 tokens, timed to the first sampled token). Single runs, so
expect a few percent of noise.

| Model | Load | Prompt processing | Generation |
| --- | ---: | ---: | ---: |
| Gemma 4 E4B | 3.0 s | 545 tok/s | 46.7 tok/s |
| Qwen3.5 9B | 3.7 s | 329 tok/s | 29.5 tok/s |
| Gemma 4 12B | 5.2 s | 205 tok/s | 22.4 tok/s |

What it means for a chat turn: the assembled context is often 5,000 to 8,000 tokens, so prompt
processing dominates the wait before the first token (about 10 to 15 s on E4B, 15 to 25 s on
Qwen, 25 to 40 s on the 12B), and a 300 token answer adds 6, 10 or 13 s. Sub-agent calls are
short prompts with forced tool calls, which is why they stay on E4B.
