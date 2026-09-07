# Local tokens per second, 2026-09-07: the 26B A4B joins the table

Measured on the user's laptop (M4 Pro, 24 GB) with llama-cpp-python, Metal, all layers on the
GPU, one model loaded at a time. Same scripts as the 2026-09-06 run (`/tmp/fq-tps-67/bench.py`
and `prompt.py`, copies of `/tmp/fq-tps/`): generation is greedy, 256 tokens after a 366 token
prompt; prompt processing is about 3,000 tokens timed to the first sampled token. Single runs.
E4B and the 12B are Q4_K_M; the 26B A4B is the UD-Q3_K_XL the catalog ships (ticket 67).

| Model | Load | Prompt processing | Generation |
| --- | ---: | ---: | ---: |
| Gemma 4 E4B | 3.0 s | 519 tok/s | 45.4 tok/s |
| Gemma 4 12B | 6.0 s | 205 tok/s | 22.3 tok/s |
| Gemma 4 26B A4B (UD-Q3_K_XL) | 12.8 s | 480 tok/s | 38.1 tok/s |

The 26B A4B is a mixture of experts with about 4B parameters active per token, which is why it
generates faster than the dense 12B and reads a prompt almost as fast as E4B, although its file
is 12.9 GB.

## The pair does not fit

The app keeps Gemma 4 E4B resident in the fast seat and the chosen chat model in the other. With
E4B and the 26B loaded together, the first decode failed with `llama_decode returned -3` (an
allocation failure inside llama.cpp) at 32k and again at 16k context. `finquery-check`'s pair
report said "ok" for the same pair because it reads the process RSS, which on this machine came
back as 0.1 GB with the 26B mmapped, so that figure is not to be trusted for a model of this
size; the decode failure is. E4B with the 12B loaded and answered as before at 32k.

So on a 24 GB Mac the 26B runs alone, at the numbers above, and not beside E4B. Swap was already
at 11.5 GB of 13.3 GB when the test began, with the usual desktop open.
