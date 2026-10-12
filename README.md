# Portima × anyformat: document intelligence starter

Turn **European accident statements** and **car order forms** into structured data with
[anyformat](https://anyformat.ai), then measure it field by field: accuracy, confidence thresholds,
and what a broker still has to check.

**Start with the context pack: [`docs/context-pack.pdf`](docs/context-pack.pdf)** (25 slides: the challenge, setup,
how it works, the data contract, what you can build, how to measure it, limits). Its agent-readable twin is
[`CONTEXT.md`](CONTEXT.md).

Everything in `samples/` is synthetic. Every name, plate, VIN and policy number is invented. The
samples come with their correct answers, so you can check your setup end to end before you touch a
real document.

## Five minutes to a scored run

```bash
git clone https://github.com/anyformat-ai/portima-hackathon-starter && cd portima-hackathon-starter
cp .env.example .env                 # paste your key from https://app.anyformat.ai/api-key
uv sync                              # needs uv: https://docs.astral.sh/uv/
uv run af.py create order_form       # creates 2 workflows in your workspace
uv run af.py run order_form          # runs the 6 sample order forms
uv run af.py score order_form        # accuracy per field + threshold sweep -> reports/
```

Then the same three commands with `accident_statement`.

**What "correct" looks like:**
- `run` prints a review link per document. Open one to see the fields highlighted on the page.
- `order_05_modern_nl_bad_total.pdf` reports a failed **Net + VAT = total** validation. Its printed
  total is 100 euros too high on purpose.
- On the scanned accident statements, the fields that come back wrong are also the ones with the
  lowest confidence. That's what the threshold sweep in `reports/` measures.

## With a coding agent

The repo is set up for one. `AGENTS.md` (Codex, Cursor, others) and `CLAUDE.md` (Claude Code)
tell the agent where to start.

```bash
# Claude Code: .mcp.json is already here; export the key and start
export ANYFORMAT_API_KEY=af_...
claude

# Codex
codex mcp add anyformat --url https://api.anyformat.ai/mcp
# then add the header block from docs/codex-config.toml to ~/.codex/config.toml
codex
```

Prompts to start with:
- *"Run the order form check from AGENTS.md and explain the report."*
- *"Which accident statement fields are below 90% accuracy, and why? Propose better descriptions."*
- *"Draft ground truth for the PDFs in ./our_docs following docs/GROUND_TRUTH.md."*

## The commands

| Command | What it does |
|---|---|
| `af.py create <type>` | Creates one workflow per file in `workflows/<type>/` (parse **fast** → extract **standard** → validate) |
| `af.py run <type> [pdfs]` | Sends each PDF to every workflow of the type, merges the fields into `results/<type>/` |
| `af.py score <type>` | Compares `results/` to `ground_truth/`: accuracy per field, plus a confidence threshold sweep |
| `af.py ground-truth <type>` | Writes the ground truth in the dataset API format into `ground_truth/_api/` |
| `af.py dataset <type>` | Uploads each PDF + its ground truth to each workflow's dataset |
| `af.py eval <type>` | Runs anyformat's own evaluation on those datasets |

## How it is built

**Why several workflows per document?** Rule of thumb: about 20 fields per extract, because long
schemas extract worse than short ones, and a workflow holds one extract. The accident statement has ~100 fields, so it is six workflows:
- accident & sketch
- vehicle A (policyholder, vehicle, insurer)
- vehicle B (policyholder, vehicle, insurer)
- drivers & damage
- circumstances A
- circumstances B

`af.py run` merges them back into one record per document.

**Cost.** Fast parse (12) + standard extract (35) is about 47 credits a page per workflow:
- One accident statement through six workflows: ~280 credits.
- One order form through two workflows: ~95 credits.
- All 12 samples: ~2,300 credits.

**Validation rules** (in each workflow JSON, deterministic, free):
- **Order form:**
  - net + VAT = total
  - base + options − discount = net
  - option lines add up to the options total
  - the VIN is 17 valid characters
- **Accident statement:**
  - the accident date is not in the future
  - the plate looks Belgian
  - the plate was read with confidence of 80 or more
  - the policy number is present
  - birth dates are plausible
  - each column ticked between 1 and 17 boxes

## Docs

- [`docs/context-pack.pdf`](docs/context-pack.pdf): the context pack as slides, for people
- [`CONTEXT.md`](CONTEXT.md): the same context pack, for your coding agent
- [`docs/WORKSPACE.md`](docs/WORKSPACE.md): what you'll see in app.anyformat.ai and where
- [`docs/GROUND_TRUTH.md`](docs/GROUND_TRUTH.md): make ground truth for real documents with Claude, then have a broker check it
- [`docs/OPTIMIZER.md`](docs/OPTIMIZER.md): dataset → evaluation → optimizer
- Regenerate the samples: `uv run --group samples python tools/make_samples.py`
