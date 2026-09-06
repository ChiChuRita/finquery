# The three local candidates on the HPI cluster

Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B, Q4_K_M through llama-cpp with CUDA, one RTX PRO 6000
per job, 32k context, the same wire formats and the same sub-agent paths the laptop runs. The
seconds are seconds on that one GPU, which is not the laptop's: the tokens per second table
below is what the laptop costs.

The SQL and chart tables are the primary numbers: they score the sub-agent, which is where an
adapter attaches. The end-to-end table runs the whole chat turn in front of the sub-agent on 30
training cases, so the gap between the two is routing and phrasing loss.

### sql set

| model | n | figure match | SQL valid | first attempt | median s | total s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 5 | 100 % | 100 % | 80 % | 6.4 | 58 |


### chart set

No run of this set has come back yet.

### e2e set

| model | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | total s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 30 | 47 % | 77 % | 87 % | 93 % | 100 % | 80 % | 47 % | 31.8 | 965 |


## What each pair costs on the laptop

From `bench/results/20260906-local-tokens-per-second.md`, measured on the user's Mac with
Metal. The fast slot is Gemma 4 E4B either way, so the pair is E4B plus the chat model.

| pair | generation | prompt processing | both models at 32k |
| --- | ---: | ---: | ---: |
| E4B alone | 46.7 tok/s | 545 tok/s | 5.9 GB |
| E4B + Qwen3.5 9B | 29.5 tok/s | 329 tok/s | 13.5 GB |
| E4B + Gemma 4 12B | 22.4 tok/s | 205 tok/s | 12.9 GB |

## The decision rule

Accuracy first: the pair is the one with the highest figure match on the SQL set, then on the
chart set. Speed breaks a tie only inside about five points. The pair has to fit in about
13.5 GB, which is what the 24 GB Mac has left for weights and KV cache with both models
resident, so a pair that does not fit is not a candidate whatever it scores.
