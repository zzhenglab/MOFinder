# Cleaned synthesis data

These tables preserve the cleaned positive and negative records used for dataset preparation, before training and holdout filtering.

| Folder | Contents |
| --- | --- |
| [archived](archived/) | 15,340 positive records and 15,063 negative records used to reproduce the archived datasets |
| [linker_corrected](linker_corrected/) | The same 15,063 negative records with documented linker prime symbols restored; uses the archived positive table |

Both versions are retained because linker-name corrections can affect grouping. Prepared training and holdout records are stored in [training](../training/).
