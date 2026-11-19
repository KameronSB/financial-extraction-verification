# Financial table extraction and verification

How much can you trust a financial figure when a language model cites the table cell it came from? This Python project asks GPT-6 Luna to extract a value, its scale and its source coordinates from a financial table. A verifier checks the citation, and an offline evaluator compares the answer with the TAT-QA reference.

## Results

Both saved runs cover the full development and test splits of a custom **direct numeric table-cell subset**. A reference match requires the reported numeric value and scale to agree. The last column measures agreement among answers the verifier accepted. [Development summary](results/dev-full.summary.json) · [Test summary](results/test-full.summary.json)

| Split | Matched reference / all questions | Passed verification / all questions | Matched reference / passed |
| --- | ---: | ---: | ---: |
| Development | 216/233 (92.7%) | 233/233 (100%) | 216/233 (92.7%) |
| Held-out test | 194/211 (91.9%) | 208/211 (98.6%) | 194/208 (93.3%) |

On the test split, the verifier flagged three cases. The model abstained twice. In the third case, the model returned the year **2019** while its cited cell contained **2014**. Fourteen answers passed the checks and still disagreed with the reference. [Flagged citation](results/test-full.json#L9167) · [Test predictions](results/test-full.json)

One disagreement illustrates why the original table matters. Asked for issued and paid-up capital in 2019, the model returned **83,692** in thousands. The cited row lists **83,692** under 2019 and **66,128** under 2018. The reference expects **66,128**, so this answer counts as a miss even though the 2019 column supports it. [Source table](results/test-full.json#L4389) · [Prediction and reference](results/test-full.json#L4464) · [Read the case study](docs/case-study.md)

## Reproduce the scores offline

From the repository root, run these commands with Python 3.12 (on Windows, use `py -3.12` in place of `python3`). The evaluator uses only the standard library and the saved predictions. It prints each summary and writes it beside the input as `*.summary.json`.

```sh
python3 evaluate.py results/test-full.json
python3 evaluate.py results/dev-full.json
```

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
2. **Extract and verify.** The model receives the question, indexed table and paragraphs. It returns a structured prediction. Python checks the cited coordinates, numeric agreement, the supported scale labels and explicit percent signs. The value stays in reported units, so `4.6%` has value `4.6`, scale `percent` and a derived ratio of `0.046`. [Extraction](extract.py) · [Verifier](verify.py)
3. **Score.** Reference answers are used for subset selection and offline scoring. A pass establishes that the predicted number matches the cited cell. Choosing the intended year, metric and unit can require interpreting headings or surrounding text. The evaluator scores value and scale only. Overall rates use all planned questions, including unprocessed questions in a partial run. Each run records its prompt and dataset hashes, settings and per-question outputs. [Runner](run.py) · [Evaluator](evaluate.py)

## Dataset and attribution

The dataset is adapted from TAT-QA by Zhu et al. (ACL 2021), distributed under CC BY 4.0. This project filters the source as described above and assigns the percent scale to reference answers with an explicit percent sign. [TAT-QA](https://github.com/NExTplusplus/TAT-QA) · [Paper](https://aclanthology.org/2021.acl-long.254/) · [Dataset licence](https://creativecommons.org/licenses/by/4.0/)

To rebuild the subset, run `python3 prepare_data.py`. It checks the raw files against SHA-256 digests pinned to upstream commit `870accc41953dcde885aabeb963d94aabdc0fbc3`, downloads missing source files, and writes the prepared splits and manifest. [Dataset manifest](data/manifest.json)
