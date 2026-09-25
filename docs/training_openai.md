# Model training: GPT-4.1 in the OpenAI dashboard

The GPT-4.1 training workflow uses the OpenAI fine-tuning interface. The settings are recorded in [training_openai.json](../configs/training_openai.json), which is a manual training recipe. Dataset preparation is described in [datasets.md](datasets.md).

## Input files

| File | Records | Purpose |
| --- | ---: | --- |
| [data/final_json/train.jsonl](../data/final_json/train.jsonl) | 23,528 | Training examples |
| [data/final_json/holdout.jsonl](../data/final_json/holdout.jsonl) | 2,595 | Holdout evaluation; optional validation metrics during training |

Each line is a complete JSON object containing `system`, `user`, and `assistant` messages. The assistant message contains the reference label, `P` or `N`. Upload the `.jsonl` file directly, without converting it to a JSON array. File hashes and label counts are recorded in the [training manifest](../data/final_json/manifest.json).

The system message uses the full [reaction-prediction instructions](../prompts/training/reaction_prediction.txt), shared with dataset preparation, MOF Quest evaluation, and HPC training. Renaming the prompt file preserves its text and the existing training and holdout JSONL bytes.

## Create the job

1. Open the [OpenAI fine-tuning dashboard](https://platform.openai.com/finetune) and select the project used for training.
2. Select **Create**, choose **Supervised** fine-tuning, and select **GPT-4.1** (`gpt-4.1-2025-04-14`).
3. Upload `data/final_json/train.jsonl` under **Training data**.
4. If validation metrics are required during training, select `data/final_json/holdout.jsonl` under **Validation data**. Otherwise leave the validation field empty and use the holdout for subsequent evaluation. Record the selection with the job details.
5. Enter the settings below and create the job.

| Setting | Value |
| --- | --- |
| Epochs | 2 |
| Batch size | 15 |
| Learning-rate multiplier | 2 |
| Seed | 42 |

Use two epochs for the two-epoch run. For the one-epoch run, change only **Epochs** to **1**. With 23,528 records and a batch size of 15, the one-epoch run has approximately 1,569 steps (`ceil(23528 / 15)`); two epochs have approximately 3,138 steps. Keep a separate job record and output model ID for each run, including the platform's reported step count.

## Save the result and evaluate

After the job completes, save the job ID, uploaded file IDs, resolved settings, training metrics, and output model ID alongside the input file hashes. Include the validation-file selection in this record. The output model ID begins with `ft:` and identifies the trained model used for evaluation.

Set this model ID in [holdout_evaluation.json](../configs/holdout_evaluation.json) or the relevant group in [quest_evaluation.json](../configs/quest_evaluation.json), using an account with access to the trained model. Give each evaluation a distinct output name. The [holdout evaluation guide](holdout_evaluation.md) and [22-question evaluation guide](quest_evaluation.md) describe the commands and saved predictions.

## OpenAI documentation

- [Supervised fine-tuning](https://developers.openai.com/api/docs/guides/supervised-fine-tuning): JSONL format, dashboard submission, and job monitoring.
- [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1): model snapshot and fine-tuning support.
- [Fine-tuning job parameters](https://developers.openai.com/api/reference/resources/fine_tuning/subresources/jobs/methods/create): hyperparameters, seed, and optional validation data.
