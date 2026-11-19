# Financial table extraction and verification

How much can you trust a financial figure when a language model cites the table cell it came from? The extractor asks GPT-6 Luna to select a source cell. Python copies the reported value, looks for unit evidence in the table and its captions, and sends unresolved cases to review. The repository includes the original model outputs, an offline replay of their cell choices, and a fresh end-to-end test run.

## Results

### Source-based verification

The replay uses the original cell selections on all 444 questions. It applies the revised unit, period and metric checks and preserves the original abstentions and failed citations. A strict match requires the reported number and scale to match the dataset reference. An unresolved scale counts as a strict miss. [Development replay](results/dev-full.replay.summary.json) · [Test replay](results/test-full.replay.summary.json)

| Split and processing | Strict matches / all | Accepted / all | Strict matches / accepted | Accepted reference misses |
| --- | ---: | ---: | ---: | ---: |
| Development baseline | 216/233 (92.7%) | 233/233 (100%) | 216/233 (92.7%) | 17 |
| Development replay | 206/233 (88.4%) | 214/233 (91.8%) | 206/214 (96.3%) | 8 |
| Test baseline | 194/211 (91.9%) | 208/211 (98.6%) | 194/208 (93.3%) | 14 |
| Test replay | 164/211 (77.7%) | 173/211 (82.0%) | 163/173 (94.2%) | 10 |
| Test live, revised selector | 165/211 (78.2%) | 174/211 (82.5%) | 164/174 (94.3%) | 10 |

The revised selector returned valid responses on all 211 fresh test requests. The reported number matched the reference on 205 questions (97.2%). Of the 37 cases sent to review, 34 lacked a resolved unit, two cited a year heading that needed review, and one was an abstention. The live selector recovered the 2017 current state income-tax provision of 3 million, adding one strict match over replay. [Full live run](results/test-cell-selection-full.json) · [Live test summary](results/test-cell-selection-full.summary.json)

On test, the replay improved reference agreement among accepted answers by 0.9 percentage points. It sent 38 answers to review, including 30 that the original run had accepted and scored correctly. Of the 38, 34 had unresolved units, one selected a year heading requiring review, and three had already failed the baseline checks. One reviewed answer still matched the reference. Numeric-only agreement was 204/211 in both runs. This trade-off matters if every question needs an automatic answer. [Test replay details](results/test-full.replay.summary.json)

On the first ten development questions, all ten live selections matched the reference number. Seven had a supported scale and matched the full reference. Three went to review for missing unit evidence. [Development run](results/dev-cell-selection-10.json) · [Development summary](results/dev-cell-selection-10.summary.json)

The development audit covers 13 deliberately selected cases, including reference disagreements, a missing scale, and mixed-unit headings. The baseline accepted all 13, with source support for both the cell and scale in eight. The replay accepted all 12 source-supported answers and sent the remaining case to review. It also flagged both deliberately substituted cells with the same number but the wrong year or metric. This diagnostic sample tests known failure modes. [Review annotations](data/dev-evidence.json) · [Audit results](results/dev-full.audit.json)

### Published baseline

The published baseline used model-supplied values, coordinates and scales on the full development and test splits of a custom **direct numeric table-cell subset**. [Development summary](results/dev-full.summary.json) · [Test summary](results/test-full.summary.json)

On the test split, the verifier flagged three cases. The model abstained twice. In the third case, the model returned the year **2019** while its cited cell contained **2014**. Fourteen answers passed the checks and still disagreed with the reference. [Flagged citation](results/test-full.json#L9167) · [Test predictions](results/test-full.json)

One disagreement illustrates why the original table matters. Asked for issued and paid-up capital in 2019, the model returned **83,692** in thousands. The cited row lists **83,692** under 2019 and **66,128** under 2018. The reference expects **66,128**, so this answer counts as a miss even though the 2019 column supports it. [Source table](results/test-full.json#L4389) · [Prediction and reference](results/test-full.json#L4464)

## Reproduce the scores offline

From the repository root, run these commands with Python 3.12 (on Windows, use `py -3.12` in place of `python3`). The evaluator uses only the standard library and the saved predictions. It prints each summary and writes it beside the input as `*.summary.json`.

```sh
python3 evaluate.py results/test-full.json
python3 evaluate.py results/dev-full.json
python3 evaluate.py results/test-cell-selection-full.json
```

Replay the revised processing on the saved selections and run the development evidence audit with the standard library.

```sh
python3 evaluate.py results/dev-full.json --replay
python3 evaluate.py results/test-full.json --replay
python3 audit.py results/dev-full.json
```

The replay commands write separate summaries for the [development](results/dev-full.replay.summary.json) and [test](results/test-full.replay.summary.json) splits. The audit checks source cells and reporting scales in 13 manually reviewed development examples. [Review annotations](data/dev-evidence.json) · [Audit results](results/dev-full.audit.json)

For a single worked example, follow the 2019 total sales question from the table's “in millions” caption to the cited cell containing $1,496.5. [Sample prediction](results/sample.json)

## Run a new extraction

Install the locked dependencies with `uv sync --locked --python 3.12`. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. The project reads `.env` ahead of process variables. The published runs used `OPENAI_MODEL=gpt-6-luna`. [Environment template](.env.example)

Start with ten development questions. These commands use the committed, prepared data. Each extraction makes live API requests and needs a fresh output filename.

```sh
uv run python run.py --split dev --limit 10 --out results/local/dev-10.json
uv run python evaluate.py results/local/dev-10.json
```

Use development examples when changing the prompt. To run the entire test split after choosing a design, set `--limit 0`.

```sh
uv run python run.py --split test --limit 0 --out results/local/test-full.json
uv run python evaluate.py results/local/test-full.json
```

## Method and scope

1. **Select questions.** Keep single-span table or table-and-text questions that require no comparison and whose signed reference value matches at least one complete numeric cell. This yields 1,818 training, 233 development and 211 test questions. The results apply to questions with a reference value in a prepared table. PDF parsing and detecting unanswerable questions would need separate evaluations. [Selection code](prepare_data.py)
2. **Select the source cell.** The model receives the question, indexed table and paragraphs. It returns a cell ID or abstains. Python looks up the ID, copies the cell text, and checks supported period and metric constraints. [Extraction](extract.py) · [Verifier](verify.py)
3. **Resolve the unit.** Look for evidence in the cell, its applicable headings and surrounding table declarations. Preserve the source unit and the evidence used to assign a reporting scale. An explicit base unit has scale `""`. An unresolved or conflicting scale has value `null` and goes to review. A verified percent such as `4.6%` has a derived ratio of `0.046`. [Unit resolution](units.py)
4. **Evaluate the answer.** Compare the reported number and scale with the published reference. Report accepted accuracy alongside coverage. Overall rates use all planned questions, which can include unprocessed questions in a partial run. The development audit additionally checks cell coordinates against reviewed source locations. Reference labels enter only dataset preparation and evaluation. [Evaluator](evaluate.py) · [Source audit](audit.py)

## Dataset and attribution

The dataset is adapted from TAT-QA by Zhu et al. (ACL 2021), distributed under CC BY 4.0. This project filters the source as described above and assigns the percent scale to reference answers with an explicit percent sign. [TAT-QA](https://github.com/NExTplusplus/TAT-QA) · [Paper](https://aclanthology.org/2021.acl-long.254/) · [Dataset licence](https://creativecommons.org/licenses/by/4.0/)

To rebuild the subset, run `python3 prepare_data.py`. It checks the raw files against SHA-256 digests pinned to upstream commit `870accc41953dcde885aabeb963d94aabdc0fbc3`, downloads missing source files, and writes the prepared splits and manifest. [Dataset manifest](data/manifest.json)
