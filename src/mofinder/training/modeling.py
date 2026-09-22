"""LoRA fine-tuning on the final-position N and P token logits."""

from pathlib import Path

import torch
import torch.nn as nn
from datasets import Dataset
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, DataCollatorWithPadding
from transformers.modeling_outputs import SequenceClassifierOutput

from .records import render_prompt, tokenize_prompts


def make_dataset(rows, tokenizer, max_length, reaction_prompt=None):
    rendered = []
    for row in rows:
        item = {
            "text": render_prompt(row, reaction_prompt),
            "labels": row["labels"],
        }
        if "numeric_features" in row:
            item["numeric_features"] = row["numeric_features"]
        rendered.append(item)
    raw = Dataset.from_list(rendered)

    def tokenize(batch, indices):
        return tokenize_prompts(batch["text"], tokenizer, max_length, indices)

    return raw.map(tokenize, batched=True, with_indices=True, batch_size=256, remove_columns=["text"])


class PnDataCollator:
    def __init__(self, tokenizer):
        self.base = DataCollatorWithPadding(tokenizer=tokenizer, pad_to_multiple_of=8)

    def __call__(self, features):
        features = [dict(feature) for feature in features]
        numeric = None
        if features and "numeric_features" in features[0]:
            numeric = [feature.pop("numeric_features") for feature in features]
        batch = self.base(features)
        if numeric is not None:
            batch["numeric_features"] = torch.tensor(numeric, dtype=torch.float32)
        return batch


def prepare_base(base, gradient_checkpointing):
    base.config.use_cache = False
    if gradient_checkpointing:
        base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        base.enable_input_require_grads()
    return base


def make_lora_config(args, task_type):
    target_modules = [
        module.strip() for module in args.lora_target_modules.split(",") if module.strip()
    ]
    if not target_modules:
        raise ValueError("--lora-target-modules must contain at least one module name")
    target_parameters = [
        parameter.strip()
        for parameter in args.lora_target_parameters.split(",")
        if parameter.strip()
    ]
    return LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=target_modules,
        target_parameters=target_parameters or None,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type=task_type,
    )


def classification_loss(logits, labels, class_weights, focal_gamma, label_smoothing=0.0):
    if not 0.0 <= label_smoothing < 1.0:
        raise ValueError("--label-smoothing must be in [0, 1)")
    weights = class_weights.to(logits.device)
    if focal_gamma <= 0.0:
        return nn.functional.cross_entropy(
            logits, labels, weight=weights, label_smoothing=label_smoothing
        )
    per_example = nn.functional.cross_entropy(
        logits, labels, weight=weights, reduction="none", label_smoothing=label_smoothing
    )
    target_probability = torch.softmax(logits.float(), dim=-1).gather(
        1, labels.unsqueeze(1)
    ).squeeze(1)
    return (((1.0 - target_probability) ** focal_gamma) * per_example).mean()


def resume_paths(args):
    root = Path(args.resume)
    if args.resume_kind == "holdout":
        return root / "best_holdout_adapter", root / "best_holdout_classifier_head.pt"
    return root / "best_adapter", root / "classifier_head.pt"


def attach_lora_backbone(base, args, task_type):
    if not args.resume:
        return get_peft_model(base, make_lora_config(args, task_type))
    adapter_path, _ = resume_paths(args)
    if not args.resume_merge_and_reinit_lora:
        return PeftModel.from_pretrained(base, str(adapter_path), is_trainable=True)
    parent = PeftModel.from_pretrained(base, str(adapter_path), is_trainable=False)
    merged = parent.merge_and_unload()
    return get_peft_model(merged, make_lora_config(args, task_type))


class NativeLmClassifier(nn.Module):
    def __init__(self, args, tokenizer):
        super().__init__()
        base = AutoModelForCausalLM.from_pretrained(
            args.model,
            local_files_only=True,
            dtype=torch.bfloat16,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
        prepare_base(base, args.gradient_checkpointing)
        self.backbone = attach_lora_backbone(base, args, "CAUSAL_LM")
        self.config = base.config
        self.config.num_labels = 2
        label_token_ids = []
        for label in ("N", "P"):
            token_ids = tokenizer.encode(label, add_special_tokens=False)
            if len(token_ids) != 1:
                raise ValueError(f"Expected a single token for {label!r}, got {token_ids}")
            label_token_ids.append(token_ids[0])
        self.register_buffer("label_token_ids", torch.tensor(label_token_ids, dtype=torch.long))
        self.register_buffer(
            "class_weights",
            torch.tensor([args.negative_class_weight, 1.0], dtype=torch.float32),
            persistent=False,
        )
        self.focal_gamma = args.focal_gamma
        self.label_smoothing = getattr(args, "label_smoothing", 0.0)

    def forward(self, input_ids, attention_mask=None, labels=None, **kwargs):
        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            return_dict=True,
            use_cache=False,
            logits_to_keep=1,
        )
        token_logits = outputs.logits[:, -1].float()
        logits = token_logits.index_select(-1, self.label_token_ids.to(token_logits.device))
        loss = None
        if labels is not None:
            loss = classification_loss(
                logits, labels, self.class_weights, self.focal_gamma, self.label_smoothing
            )
        return SequenceClassifierOutput(loss=loss, logits=logits)


def model_device(model):
    return next(model.parameters()).device
