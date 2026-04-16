# midi_gen_ai_rewrite

This is a clean rewrite of the old frame-level project.

## Core idea

The old piano-roll next-frame setup was abandoned. This version uses an event sequence representation that is standard in symbolic music modeling:

- `NOTE_ON`
- `NOTE_OFF`
- `TIME_SHIFT`
- `VELOCITY`

That gives the LSTM a compact token stream instead of a sparse 127-dim frame.

## Files

- `train.py`: train the token LM
- `generate.py`: sample a MIDI continuation from a checkpoint
- `evaluate.py`: compute loss/perplexity and objective generation metrics
- `src/tokenizer.py`: MIDI <-> event token conversion
- `src/dataset.py`: MAESTRO token window dataset
- `src/model.py`: LSTM language model

## Quick start

Train:

```bash
python c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/train.py \
  --dataset-root c:/Users/he/Documents/Arduino/midi_gen_ai/dataset/maestro-v3.0.0 \
  --run-dir c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/runs/event_lm_v1 \
  --seq-len 1024 \
  --stride 512 \
  --batch-size 8 \
  --epochs 20 \
  --num-workers 0
```

Smoke test:

```bash
python c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/train.py \
  --dataset-root c:/Users/he/Documents/Arduino/midi_gen_ai/dataset/maestro-v3.0.0 \
  --run-dir c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/runs/event_lm_smoke \
  --seq-len 512 \
  --stride 256 \
  --batch-size 4 \
  --epochs 1 \
  --embed-dim 128 \
  --hidden-dim 256 \
  --num-layers 2 \
  --dropout 0.1 \
  --num-workers 0 \
  --max-train-files 1 \
  --max-validation-files 1 \
  --max-test-files 1
```

Generate:

```bash
python c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/generate.py \
  --checkpoint c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/runs/event_lm_v1/best.pth \
  --prompt-midi c:/path/to/prompt.mid \
  --output-midi c:/path/to/output.mid
```

Evaluate:

```bash
python c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/evaluate.py \
  --checkpoint c:/Users/he/Documents/Arduino/midi_gen_ai_rewrite/runs/event_lm_v1/best.pth \
  --split validation
```

The evaluation report includes:

- split loss and perplexity
- token repeat rate
- token entropy and unique-token ratio
- MIDI note count, pitch range, note rate, and polyphony summary

## Notes

- No compatibility with the old frame-based code is preserved.
- No 24 fps assumptions remain.
- The old temporary scripts and smoke-test outputs were cleaned before this rewrite started.
- Tokenized MAESTRO files are cached on disk under `dataset_root/.event_token_cache` by default.
- Use `--rebuild-cache` on `train.py` if you want to refresh the cached token files.

## Committed Showcase Artifacts

The repository includes a small set of V2 showcase artifacts for demos and quick listening checks:

- Checkpoint: `runs/event_lm_v2/best.pth`
- Prompt-sensitivity audition set: `runs/event_lm_v2/audition_prompt_sensitivity/`

Everything else under `runs/` is still intended to be local experiment output unless explicitly whitelisted.
