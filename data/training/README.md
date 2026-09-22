# Fine-tuning-ready records

`train.jsonl` and `holdout.jsonl` contain the archived training and validation records, unchanged. File identities and label counts are recorded in `manifest.json`. [Split assignments and parameters](../splits/README.md) identify the retained source rows and chemical groups in each partition.

| Dataset | P | N | Total |
| --- | ---: | ---: | ---: |
| Training | 11,968 | 11,560 | 23,528 |
| Validation/holdout | 1,320 | 1,275 | 2,595 |

Each record contains the original system instruction, eight-field reaction conditions, and a P/N reference answer. The files match the outputs from the source dataset-preparation notebook. They are ready as training and validation inputs; no training job is launched by the repository preparation commands.

See [dataset preparation](../../docs/datasets.md) to regenerate records and [holdout evaluation](../../docs/holdout_evaluation.md) to evaluate a configured model. Live evaluation sends only the system instruction and reaction conditions. The reference answer is retained locally for scoring.

Training routes:

- [GPT-4.1 in the OpenAI dashboard](../../docs/training_openai.md): upload the training JSONL and enter the recorded hyperparameters.
- [GPT-oss-20B on a local GPU or HPC system](../../docs/training_hpc.md): prepare one dataset bundle, transfer it to the training environment, and train a LoRA adapter.
