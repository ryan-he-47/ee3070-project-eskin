# midi_gen_ai_rewrite project context

This folder is the active line of work for the symbolic MIDI continuation project.

## 1. Project status

The project has moved from the old frame-level piano-roll approach to an event-token LSTM language model.

Current focus:

1. Keep a stable, reproducible continuation baseline.
2. Improve generation robustness (reduce collapse patterns).
3. Prepare for USB-MIDI real-time continuation integration.

## 2. Representation and model

Each MIDI is tokenized with:

- `NOTE_ON`
- `NOTE_OFF`
- `TIME_SHIFT`
- `VELOCITY`

Core model:

- Embedding + 2-layer LSTM + projection head
- Trained with next-token cross-entropy

## 3. Main files

- `train.py`: train token LM
- `generate.py`: continuation generation
- `evaluate.py`: objective evaluation (loss, ppl, token/midi stats)
- `src/tokenizer.py`: MIDI <-> tokens
- `src/dataset.py`: MAESTRO token windows + cache support
- `src/model.py`: event LSTM LM

## 4. Data path and token cache

Dataset path:

- `c:/Users/he/Documents/Arduino/midi_gen_ai/dataset/maestro-v3.0.0`

Token cache:

- default: `c:/Users/he/Documents/Arduino/midi_gen_ai/dataset/.event_token_cache`
- memory-mapped `.npy` files grouped by split and tokenizer config
- supported by `--cache-dir` and `--rebuild-cache`

Observed cache benefit on small sample:

- first build about `4.34s`
- reload about `0.02s`

## 5. Runs and checkpoints (important)

### v1

- Run dir: `runs/event_lm_v1`
- Best val-loss checkpoint: `best.pth` (around early epoch)
- Subjectively better listening checkpoint in several trials: `last.pth`

### v2

- Run dir: `runs/event_lm_v2`
- Smaller model variant trained with stronger regularization
- 12-epoch run completed with smoother val-loss trend

Key lesson:

- better val-loss does not guarantee better continuation musicality

## 6. Generation behavior findings

Common failure modes observed in both v1 and v2 under some prompts/decoding:

1. long-note stall
2. long silence section
3. short-loop/heartbeat-like repetition
4. occasional post-collapse recovery ("revival")

Interpretation:

- model learned valid "musical pause" behavior but over-triggers it in some contexts
- prompt structure and decoding parameters can strongly amplify or reduce collapse

## 7. Prompt sensitivity findings

For v2, fixed checkpoint + fixed decoding with different prompt windows showed strong sensitivity:

- some prompts produce active, varied continuation
- some prompts with long-time-span/slow ending are much more likely to collapse

Prompt duration note:

- `prompt_window_len` fixed by token count does not mean fixed seconds

## 8. Baseline parameters to keep

Current preserved fallback baseline (used for fair A/B with v1 last):

- checkpoint: `runs/event_lm_v1/last.pth`
- `min_new_tokens=160`
- `min_new_seconds=10`
- `max_new_tokens=1200`
- `context_len=512`
- `temperature=1.0`
- `top_k=8`
- `top_p=0.95`

Stored example:

- `runs/event_lm_v2/audition_compare/v1_last_compare.json`

## 9. Evaluation policy (practical)

Do not select checkpoints by loss only.

Use combined criteria:

1. val loss / perplexity trend
2. token-level stats (repeat rate, entropy, unique ratio)
3. continuation listening tests under fixed prompt and fixed decoding
4. collapse frequency and recovery time

## 10. USB-MIDI real-time continuation plan

Next milestone: integrate model continuation with live USB-MIDI stream.

Implementation plan:

1. Input path
	- capture incoming note events from USB-MIDI
	- convert to event tokens in near real-time

2. Context manager
	- maintain rolling token context buffer
	- apply truncation policy (`context_len`) and timing consistency

3. Real-time generation loop
	- generate short continuation chunks with bounded latency
	- enforce anti-collapse guards (min activity, silence cap, repetition guard)

4. Output path
	- send generated MIDI events back to output port/device
	- keep clock/timing aligned with host tempo domain

5. Safety fallback
	- if generation confidence or activity drops too much, fall back to pass-through or conservative mode

6. Stage metrics
	- end-to-end latency
	- dropped/late event rate
	- subjective continuity with live playing

## 11. Suggested commands

Smoke:

```powershell
E:/MiniConda/envs/fkdata/python.exe c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/train.py --dataset-root c:/Users/he/Documents/Arduino/midi_gen_ai/dataset/maestro-v3.0.0 --run-dir c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/runs/event_lm_smoke --seq-len 512 --stride 256 --batch-size 4 --epochs 1 --embed-dim 128 --hidden-dim 256 --num-layers 2 --dropout 0.1 --num-workers 0 --max-train-files 1 --max-validation-files 1 --max-test-files 1
```

Formal v1:

```powershell
E:/MiniConda/envs/fkdata/python.exe c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/train.py --dataset-root c:/Users/he/Documents/Arduino/midi_gen_ai/dataset/maestro-v3.0.0 --run-dir c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/runs/event_lm_v1 --seq-len 1024 --stride 512 --batch-size 8 --epochs 20 --embed-dim 256 --hidden-dim 512 --num-layers 2 --dropout 0.1 --num-workers 0
```

If needed once, add `--rebuild-cache` to force token cache refresh.
