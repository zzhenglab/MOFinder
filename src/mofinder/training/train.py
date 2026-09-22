#!/usr/bin/env python3
"""Fine-tune one local GPT-oss-20B model with a fresh LoRA adapter."""
import argparse
import json
import logging
import os
from pathlib import Path
import tempfile
import traceback

from .common import atomic_json, binary_metrics, export_predictions, now, sha256
from .prepare import validate_bundle
from .records import read_message_rows, read_manual_rows, render_prompt


def run(bundle, model_directory, output, save_adapter=False):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    plan = validate_bundle(bundle)
    model_directory = Path(model_directory).resolve()
    if not model_directory.is_dir():
        raise FileNotFoundError(f"Local model directory not found: {model_directory}")
    protocol = plan["protocol"]
    if (protocol["threshold"] != 0.5 or protocol["eval_every"] <= 0
            or not 0 < protocol["eval_start"] <= plan["recipe"]["max_steps"]):
        raise ValueError("Invalid fixed-threshold evaluation schedule")
    output.mkdir(parents=True, exist_ok=False)
    experiment_id = output.name
    experiment = plan["datasets"]
    result_path = output / "result.json"
    result = {"schema_version": 1, "experiment_id": experiment_id,
              "status": "running", "started_at": now(),
              "dataset": experiment, "recipe": plan["recipe"], "protocol": protocol,
              "model_directory": str(model_directory),
              "manifest_sha256": sha256(bundle / "manifest.json"),
              "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"), "evaluations": []}
    atomic_json(result_path, result)
    try:
        # Imports happen inside the failure boundary, so dependency errors are recorded.
        import numpy as np
        import torch
        from torch.utils.data import DataLoader
        from transformers import AutoTokenizer, Trainer, TrainerCallback, TrainingArguments, set_seed
        from . import modeling as base
        hp = dict(plan["recipe"])
        hp.update(model=str(model_directory), resume=None, resume_merge_and_reinit_lora=False)
        args = argparse.Namespace(**hp)
        set_seed(args.seed)
        torch.backends.cuda.matmul.allow_tf32 = True
        if torch.cuda.device_count() != 1:
            raise RuntimeError("Select exactly one GPU with CUDA_VISIBLE_DEVICES")
        result["runtime"] = {"torch": torch.__version__,
                             "transformers": __import__("transformers").__version__,
                             "peft": __import__("peft").__version__,
                             "gpu_name": torch.cuda.get_device_name(0)}
        for info in experiment.values():
            if sha256(bundle / info["path"]) != info["sha256"]:
                raise ValueError(f"Changed input: {info['path']}")
        tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        tokenizer.padding_side = tokenizer.truncation_side = "left"
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        with tempfile.TemporaryDirectory(prefix="mofinder-training-") as temp:
            train_path = bundle / experiment["train"]["path"]
            train_rows, prompt = read_message_rows(train_path)
            holdout_rows, _ = read_message_rows(bundle / experiment["holdout"]["path"])
            manual_rows = read_manual_rows(bundle / experiment["manual22"]["path"], prompt)
            if len(manual_rows) != 22:
                raise ValueError("Expected exactly 22 manual questions")
            short_prompt = (bundle / plan["short_prompt"]["path"]).read_text(encoding="utf-8")
            datasets = [base.make_dataset(rows, tokenizer, args.max_length, args.prompt_style, short_prompt)
                        for rows in (train_rows, holdout_rows, manual_rows)]
            eval_rows = (holdout_rows, manual_rows)
            eval_sources = (experiment["holdout"], experiment["manual22"])
            eval_prompts = [[render_prompt(row, tokenizer, args.prompt_style, short_prompt) for row in rows]
                            for rows in eval_rows]
            model = base.NativeLmClassifier(args, tokenizer)
            collator = base.PnDataCollator(tokenizer)
            protocol = plan["protocol"]

            def predict_with_scores(model, dataset):
                loader = DataLoader(dataset, batch_size=args.eval_batch_size,
                                         shuffle=False, collate_fn=collator)
                probabilities, labels, scores = [], [], []
                was_training = model.training
                model.eval()
                try:
                    with torch.inference_mode():
                        for batch in loader:
                            batch = {key: value.to(base.model_device(model)) for key, value in batch.items()}
                            labels.append(batch.pop("labels").cpu().numpy())
                            logits = model(**batch).logits.float()
                            probabilities.append(torch.softmax(logits, dim=-1)[:, 1].cpu().numpy())
                            scores.append((logits[:, 1] - logits[:, 0]).cpu().numpy())
                finally:
                    model.train(was_training)
                return tuple(np.concatenate(values) for values in (probabilities, labels, scores))

            class Evaluate(TrainerCallback):
                def on_step_end(self, training_args, state, control, model=None, **kwargs):
                    step = int(state.global_step)
                    if step < protocol["eval_start"] or (step - protocol["eval_start"]) % protocol["eval_every"]:
                        return control
                    # Evaluation must not change dropout/shuffle RNG for subsequent training.
                    import random
                    python_rng, numpy_rng = random.getstate(), np.random.get_state()
                    try:
                        with torch.random.fork_rng(devices=[torch.cuda.current_device()]):
                            event = {"step": step, "epoch": float(state.epoch), "at": now()}
                            for name, dataset, rows, source, prompts in zip(
                                    ("holdout", "manual22"), datasets[1:], eval_rows, eval_sources, eval_prompts):
                                probabilities, labels, scores = predict_with_scores(model, dataset)
                                event[name] = binary_metrics(probabilities, labels)
                                filename = "holdout_inference.jsonl" if name == "holdout" else "22q_inference.jsonl"
                                relative = Path("predictions") / f"step_{step:05d}" / filename
                                metadata = export_predictions(output / relative, rows, probabilities, labels,
                                    scores, prompts, experiment_id, step, name, source)
                                event[name]["predictions"] = {"path": relative.as_posix(), **metadata}
                    finally:
                        random.setstate(python_rng)
                        np.random.set_state(numpy_rng)
                    result["evaluations"].append(event)
                    atomic_json(result_path, result)
                    print(json.dumps(event), flush=True)
                    return control

            training_args = TrainingArguments(
                output_dir=temp, overwrite_output_dir=True,
                num_train_epochs=args.epochs, max_steps=args.max_steps,
                per_device_train_batch_size=args.batch_size,
                per_device_eval_batch_size=args.eval_batch_size,
                gradient_accumulation_steps=args.gradient_accumulation,
                learning_rate=args.learning_rate, warmup_ratio=args.warmup_ratio,
                weight_decay=args.weight_decay, lr_scheduler_type=args.lr_scheduler,
                bf16=True, tf32=True, eval_strategy="no", save_strategy="no",
                logging_steps=args.logging_steps, logging_first_step=True,
                report_to="none", dataloader_num_workers=0, dataloader_pin_memory=True,
                eval_accumulation_steps=16, optim="adamw_torch_fused",
                remove_unused_columns=True, seed=args.seed, data_seed=args.seed)
            trainer = Trainer(model=model, args=training_args, train_dataset=datasets[0],
                              data_collator=collator, callbacks=[Evaluate()],
                              processing_class=tokenizer)
            train_result = trainer.train(resume_from_checkpoint=None)
            expected = list(range(protocol["eval_start"], args.max_steps + 1, protocol["eval_every"]))
            if [e["step"] for e in result["evaluations"]] != expected:
                raise RuntimeError("Missing or duplicate scheduled evaluations")
            if save_adapter:
                adapter_path = output / "final_adapter"
                model.backbone.save_pretrained(adapter_path)
                tokenizer.save_pretrained(adapter_path)
                result["final_adapter"] = "final_adapter"
            result.update(status="completed", finished_at=now(),
                          final_step=int(trainer.state.global_step), train_metrics=train_result.metrics)
    except BaseException:
        result.update(status="failed", finished_at=now(), error=traceback.format_exc())
        raise
    finally:
        atomic_json(result_path, result)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--model-directory", type=Path, help="Local GPT-oss-20B model and tokenizer directory")
    parser.add_argument("--output", type=Path, help="New run directory; defaults to BUNDLE/run")
    parser.add_argument("--save-adapter", action="store_true", help="Save the final-step LoRA adapter and tokenizer")
    parser.add_argument("--validate-only", action="store_true", help="Validate input files without importing GPU libraries")
    args = parser.parse_args(argv)
    manifest = validate_bundle(args.bundle)
    if args.validate_only:
        print(json.dumps({"valid": True, "datasets": manifest["datasets"]}, indent=2))
        return
    model_directory = args.model_directory or manifest.get("model_directory")
    if not model_directory:
        parser.error("--model-directory is required for training")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    run(args.bundle, model_directory, args.output or args.bundle / "run", args.save_adapter)


if __name__ == "__main__":
    main()
