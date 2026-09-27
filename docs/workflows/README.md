# Workflow illustrations

These two author-drawn diagrams show positive synthesis extraction and negative-condition reconstruction. The original PNG exports are preserved unchanged; [provenance.json](provenance.json) records their filenames, dimensions, and checksums. See the [workflow guide](../workflow.md) for runnable commands.

## Positive synthesis extraction

![Positive extraction using article-specific text, extraction rules, and a Pydantic schema](positive_extraction.png)

Figure. Schema-constrained extraction of reported successful syntheses into article-level JSON and a table with one synthesis per row.

The article-level failure-evidence flag identifies papers to revisit during negative reconstruction; it does not label successful synthesis rows as negative. Source text and DOI provenance link the structured fields to the article.

## Negative-condition reconstruction

![Negative reconstruction from failure evidence and successful parent syntheses through modification plans and deterministic reconstruction](negative_reconstruction.png)

Figure. Evidence-conditioned reasoning produces modification plans that are applied to linked successful syntheses to reconstruct negative condition sets.

The reconstruction retains unspecified parent conditions and records the parent index, rationale, and modified classes. It enumerates the Cartesian product of permitted alternatives, so an enumerated negative row does not establish that the exact condition set was separately reported or experimentally tested. Inherited characterization fields are not independent measurements of failed syntheses.

For the corresponding implementation, see the [source code map](../source_to_code.md) and [extraction package](../../src/mofinder/extraction/).
