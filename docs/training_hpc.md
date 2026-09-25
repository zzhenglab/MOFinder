# Model training: local GPU and HPC

This workflow fine-tunes **GPT-oss-20B** on one training dataset using a fresh LoRA adapter. It uses the training and holdout files in `data/final_json/` and the current 22-question panel in `benchmarks/mof_quest/questions.json`. The [hosted GPT-4.1 training route](training_openai.md) is documented separately.

## Prepare the files

Run from the repository root. The preparation command uses the included datasets; it requires no GPU libraries or API key.

```bash
python tools/training/prepare_hpc.py --output results/local/hpc_training
python tools/training/train_hpc.py --bundle results/local/hpc_training --validate-only
```

The output contains `data/train.jsonl`, `data/holdout.jsonl`, `data/questions.jsonl`, `data/class_map.json`, and `manifest.json`. It also includes the full instructions in `prompts/reaction_prediction.txt`, copied from the shared [reaction-prediction prompt](../prompts/training/reaction_prediction.txt). Training and holdout bytes remain unchanged. Each dataset manifest entry records the row count, class counts, file size, and SHA-256 hash; the schema-version-2 manifest records the prompt path and hash under `reaction_prediction`. The question file contains the eight reaction-condition fields and a separate reference label. Training, holdout, and the 22-question panel use the same full instructions; only the conditions enter the model prompt.

Rebuild older prepared bundles with `prepare_hpc.py` into a new output directory before using the current trainer. Preserve earlier bundles and run outputs as records of their original settings.

To use another dataset, supply `--train PATH --holdout PATH`. Each JSONL record must contain a `messages` array with a user message holding the eight-field reaction-condition JSON object and an assistant answer of `P` or `N`. Use `--questions PATH` for a replacement 22-question JSON panel in the same format as the included panel. Select a new output directory for each prepared dataset.

Copy the prepared directory and this repository to the cluster using the institution's normal file-transfer method. Keep the directory structure intact. Run the validation command again after transfer with the new bundle path.

## GPU environment and model

Use a CUDA-enabled Python environment with PyTorch, Transformers, PEFT, Datasets, Accelerate, and NumPy. The runtime must support GPT-oss-20B, BF16, fused AdamW, and PEFT's `target_parameters` argument. The source training archive does not contain a dependency lock file. Reuse the working training environment and record its package versions with the results. Exact GPU memory requirements depend on the locally stored model representation and software environment.

Place the complete GPT-oss-20B model and tokenizer in a local directory. Model loading uses `local_files_only=True`; the training command does not download weights. Select one GPU within the resources allocated by the cluster scheduler.

```bash
CUDA_VISIBLE_DEVICES=0 python tools/training/train_hpc.py \
  --bundle /path/to/hpc_training \
  --model-directory /path/to/gpt-oss-20b \
  --output /path/to/run_01 \
  --save-adapter
```

Replace all `/path/to/` values before running. The output directory must be new. `--save-adapter` saves the adapter and tokenizer at the final training step. Omit it to retain only results and predictions. Each run starts from the local base model with a new adapter; interrupted training starts again from step zero.

## Training recipe

Settings are stored in `configs/training_hpc.json` and copied into the prepared manifest.

| Setting | Value |
|---|---|
| Base model | GPT-oss-20B |
| Training objective | Cross-entropy over the final-position N and P token logits |
| LoRA | Rank 32; alpha 64; dropout 0.05 |
| Target modules | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Training batch size | 24 |
| Gradient accumulation | 1 |
| Evaluation batch size | 96 |
| Learning rate | 0.00005 |
| Optimizer and schedule | Fused AdamW; cosine decay |
| Warmup ratio and weight decay | 0.03 and 0.01 |
| Optimizer steps | 5,000 |
| Prompt style | `reaction_prediction`; shared full instructions followed by condition JSON and `Label:` |
| Maximum input length | 512 tokens; left padding; overlength inputs raise an error |
| Precision | BF16; TF32 enabled |
| Training and data seed | 42 |

The positive `max_steps` value controls training duration and overrides the configured epoch count. The full prompt is stored in [`prompts/training/reaction_prediction.txt`](../prompts/training/reaction_prediction.txt):

```text
Act as an expert in reticular chemistry. You will receive reaction conditions as a JSON object with the fields:
    metal_precursor, organic_linker, modulator, solvent, metal_concentration_mM, M_L_ratio, temperature_C, and time_h.
    Based on these inputs, output exactly one uppercase label: 'P' if the conditions are likely to yield a crystalline
    metal-organic framework under experimental conditions, or 'N' if not.
```

The `reaction_prediction` renderer appends two newlines, `Reaction conditions:`, a newline, the eight-field condition JSON, two newlines, and `Label:`. The canonical prompt file contains only the instructions shown above. Reference labels remain separate from the rendered model input.

Tokenization retains the complete instructions and conditions. If any input exceeds `max_length`, increase `max_length` in `configs/training_hpc.json` and rebuild the bundle into a new output directory. This setting can increase GPU memory use; the trainer never silently truncates a reaction input.

Training labels are encoded as N = 0 and P = 1. P probability is the softmax probability over these two label logits. The classification threshold is fixed at 0.5. Both labels must correspond to single tokens in the model tokenizer.

## Evaluation and outputs

The full holdout set and the 22-question panel are evaluated at steps 2,500, 2,600, and every subsequent 100 steps through 5,000, for 26 evaluation points. Evaluation restores the random-number-generator state before training continues. These evaluations do not trigger early stopping, threshold optimization, or checkpoint selection.

`result.json` records the recipe, input hashes, runtime versions, metrics, and run status. Each evaluation writes all predictions to `predictions/step_XXXXX/holdout_inference.jsonl` and `predictions/step_XXXXX/22q_inference.jsonl`. Each row includes its source index, reference label, prediction, P probability, and raw score `logit(P) - logit(N)`. Accuracy, P-class recall, P-class F1, and the N/P confusion matrix use the same predictions. Recall and F1 are zero when their denominators are zero.

Dataset preparation and input validation run offline. GPU execution and the final-adapter export require validation in the training environment.
