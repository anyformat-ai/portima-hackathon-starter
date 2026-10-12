# Ground truth for real documents, drafted by Claude, checked by a broker

The samples already have ground truth. Real documents need it too, before anyone tunes anything:
it is the only way to know the accuracy of anyformat and of a custom approach.

**Rule: the agent drafts, a person decides.** An LLM-drafted answer key that nobody checked
measures how much two models agree, not how accurate either one is.

## 1. Put the documents in place

```
our_docs/accident_statements/claim_0001.pdf
our_docs/order_forms/order_0001.pdf
```

`our_docs/` is git-ignored. Keep real customer documents out of git.

## 2. Ask your coding agent to draft

Paste this into Claude Code or Codex from the repo root:

> For every PDF in `our_docs/accident_statements/`, read the document and write
> `ground_truth/accident_statements/<same name>.json`.
> - Use exactly the structure of `ground_truth/accident_statements/accident_01_rear_end_fr.json`:
>   same keys, same nesting, same types.
> - Fill in only what is written on the form; anything empty or illegible is `null`.
> - Dates are `YYYY-MM-DD`; checkboxes are `true`/`false`; `impact_point` and `road_layout` use the
>   enum values from the workflow JSONs.
> - Do not guess. If you are unsure of a value, keep your best reading and add its key to a
>   `"_unsure"` list at the top level.
>
> Then run `uv run af.py ground-truth accident_statement` and fix every key it reports.

The same prompt works for `order_forms`, with `order_01_classic_fr.json` as the template.

## 3. A broker checks every file

Open the PDF next to its JSON. Start with the keys in `_unsure`, then read the rest. Delete
`_unsure` when done. Plan about 5 minutes per accident statement and 2 minutes per order form.

## 4. Check the format and upload

```bash
uv run af.py ground-truth accident_statement   # converts and reports keys that don't match a workflow
uv run af.py dataset accident_statement our_docs/accident_statements/*.pdf
```

`af.py` converts the nested truth into the dataset API format for each workflow. In that format:
- every root field key is present
- every scalar is a string or `null` (`"true"`, `"2026-04-12"`, `"33450.00"`)
- object fields are lists of rows with every child key

Look in `ground_truth/_api/` to see exactly what is sent.

## How many?

**20–30 per document type** gives a stable number. Keep a third of them aside:
- **Tuning set (two thirds):** use it to pick thresholds and run the optimizer.
- **Held-out third:** report the final accuracy on these.
