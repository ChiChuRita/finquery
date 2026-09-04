# The preference loop

Using the app produces training data for the two sub-agents that will get an adapter. This
folder is the second half of that loop: it turns the records into datasets and trains one
adapter per sub-agent. Collecting is the app's job, training is a later phase, and nothing here
runs during a demo.

## The loop

1. **Collect.** Every thumb, every chart pick and every answer A/B writes a preference record
   (`src/finquery/preferences.py`): a prompt, a chosen output, a rejected output, the kind
   (`answer` or `chart`), the rating (`up`, `down`, `pick`) and the model slot. A thumb fills one
   side, a pick fills both. The Feedback page (`/feedback`) lists them and exports the whole
   table as JSONL.
2. **Export.** `export_pairs.py` reads the database and writes one file per adapter, keeping only
   the records that have both sides:

   ```sh
   uv run python training/preference/export_pairs.py --db data/finquery.db
   # chart: 12 pairs -> training/preference/data/chart.jsonl
   # query: 3 pairs  -> training/preference/data/query.jsonl
   ```

   - `chart.jsonl`: `prompt` is the chart request, the plan and the executed SQL, `chosen` and
     `rejected` are the two chart definitions. It comes from Regenerate and Pick on a chart card.
   - `query.jsonl`: `prompt` is the question the query sub-agent was given, `chosen` and
     `rejected` are two statements for it. It comes from an answer A/B in which the two runs
     wrote different SQL.

   Both files have exactly the three columns TRL's `DPOTrainer` reads.
3. **Check.** The dry run validates a dataset without a GPU and without importing torch:

   ```sh
   uv run python training/preference/train_dpo.py --adapter chart --dry-run
   ```

   It fails with one sentence on a missing column, an empty side or a pair that prefers an
   output over itself, and it warns below 32 pairs, which is where a DPO run mostly measures
   noise.
4. **Train** (later phase, needs a CUDA GPU and the training extras):

   ```sh
   pip install trl peft bitsandbytes transformers datasets accelerate
   python training/preference/train_dpo.py --adapter chart
   ```

   Gemma 4 E4B in 4-bit with a LoRA adapter of rank 16 on the attention and MLP projections,
   beta 0.1, one epoch. The base weights are the reference model, which is what makes a
   reference-free QLoRA run possible on one card.
5. **Attach.** llama.cpp wants a GGUF adapter, so the safetensors from step 4 have to be
   converted and dropped where the registry looks for it:

   ```sh
   python llama.cpp/convert_lora_to_gguf.py training/preference/runs/chart --outfile models/adapters/chart.gguf
   ```

   `finquery.local.adapters` attaches `models/adapters/{query,chart}.gguf` to the fast slot for
   the length of one sub-agent run. A missing file is a supported state: the run happens on the
   base weights and the turn carries an audit note saying so, which is also how a comparison
   between base and adapter is measured on the same weights.

## Why the prompt is what it is

The training prompt is the same text the sub-agent sees in production. For the chart adapter
that is the contract in `docs/chart-runtime.md` plus the plan and the rows, and the check in
`src/finquery/chart/selfcheck.py` is the house style written down as rules, so the same words
that repair a chart at runtime are the reward signal here. A dataset built from any other
phrasing would train a model for a prompt the app never sends.
