"""Reaction records and prompt rendering for P/N training."""

import json
from pathlib import Path

LABEL_TO_ID = {"N": 0, "P": 1}
INPUT_FIELDS = (
    "metal_precursor", "organic_linker", "modulator", "solvent",
    "metal_concentration_mM", "M_L_ratio", "temperature_C", "time_h",
)
REACTION_PROMPT_FILE = Path(__file__).resolve().parents[3] / "prompts/training/reaction_prediction.txt"


def read_reaction_prompt(path=REACTION_PROMPT_FILE):
    """Read full reaction-prediction instructions, without a conditions placeholder."""
    prompt = Path(path).read_text(encoding="utf-8")
    if not prompt.strip() or "{conditions}" in prompt:
        raise ValueError("The reaction prediction prompt must contain full instructions without a {conditions} placeholder")
    return prompt


def read_message_rows(path, limit=None):
    rows = []
    system_prompt = None
    with open(path, encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            messages = item.get("messages", [])
            prompt_messages = [message for message in messages if message.get("role") in {"system", "user"}]
            answers = [
                message.get("content", "").strip().upper()
                for message in messages
                if message.get("role") == "assistant"
            ]
            users = [message for message in prompt_messages if message.get("role") == "user"]
            if not prompt_messages or not users or not answers or answers[-1] not in LABEL_TO_ID:
                raise ValueError(f"Invalid P/N row at {path}:{line_number}")
            systems = [message for message in prompt_messages if message.get("role") == "system"]
            if system_prompt is None and systems:
                system_prompt = systems[-1].get("content", "")
            rows.append(
                {
                    "messages": prompt_messages,
                    "text": users[-1].get("content", ""),
                    "reaction": json.loads(users[-1].get("content", "{}")),
                    "labels": LABEL_TO_ID[answers[-1]],
                    "record_id": str(item.get("record_id", len(rows))),
                }
            )
            if limit is not None and len(rows) >= limit:
                break
    if not rows:
        raise ValueError(f"No rows found in {path}")
    return rows, system_prompt or "Classify the reaction conditions as P or N."


def read_manual_rows(path, system_prompt, limit=None):
    rows = []
    with open(path, encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            item = json.loads(line)
            if "messages" in item:
                prompt_messages = [
                    message
                    for message in item["messages"]
                    if message.get("role") in {"system", "user"}
                ]
                users = [message for message in prompt_messages if message.get("role") == "user"]
                answers = [
                    message.get("content", "").strip().upper()
                    for message in item["messages"]
                    if message.get("role") == "assistant"
                ]
                if not users or not answers:
                    raise ValueError(f"Invalid manual messages row at {path}:{line_number}")
                label = answers[-1]
                text = users[-1].get("content", "")
                reaction = json.loads(text)
            else:
                label = str(item.get("label", "")).strip().upper()
                text = json.dumps(
                    {field: item.get(field) for field in INPUT_FIELDS}, ensure_ascii=False
                )
                reaction = item
                prompt_messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ]
            if label not in LABEL_TO_ID:
                raise ValueError(f"Invalid manual label at {path}:{line_number}")
            rows.append(
                {
                    "messages": prompt_messages,
                    "text": text,
                    "reaction": reaction,
                    "labels": LABEL_TO_ID[label],
                    "record_id": str(item.get("record_id", f"manual22_{line_number:02d}")),
                    "difficulty": str(item.get("difficulty", "")),
                }
            )
            if limit is not None and len(rows) >= limit:
                break
    if not rows:
        raise ValueError(f"No rows found in {path}")
    return rows


def render_prompt(row, reaction_prompt=None):
    """Use the same full instructions for training and inference; exclude the answer."""
    if reaction_prompt is None:
        reaction_prompt = read_reaction_prompt()
    return f"{reaction_prompt.strip()}\n\nReaction conditions:\n{row['text']}\n\nLabel:"


def tokenize_prompts(texts, tokenizer, max_length, indices=None):
    """Reject overlength inputs rather than truncating their instructions or conditions."""
    if type(max_length) is not int or max_length < 1:
        raise ValueError("recipe.max_length must be a positive integer")
    encoded = tokenizer(texts, truncation=False, padding=False)
    for index, token_ids in enumerate(encoded["input_ids"]):
        if len(token_ids) > max_length:
            row_index = indices[index] if indices is not None else index
            raise ValueError(
                f"Reaction prediction input at row {row_index + 1} needs {len(token_ids)} tokens; "
                f"recipe.max_length is {max_length}. Increase recipe.max_length and rebuild the bundle. "
                "No prompt was truncated."
            )
    return encoded
