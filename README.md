# Financial table extraction and verification

This project uses GPT-6 Luna to answer financial questions from TAT-QA tables and accompanying text. Each answer includes a number, its reporting scale, and the source cell. Python checks that the number agrees with the cited cell. The evaluator then compares the number and scale with the reference answer. [Extraction](extract.py) · [Verification](verify.py) · [Evaluation](evaluate.py)

## Worked result

For **“What is the amount of total sales in 2019?”**, the model returned **$1,496.5 million**. It selected the “Total sales” row under the 2019 heading, at zero-based row 4, column 1. The cell contains `$1,496.5`, and the table introduction specifies millions. The answer passed verification and matched the reference on both number and scale. This is the single prediction tracked in this revision. [Sample run](results/sample.json)

Two local development runs also matched the number and scale on **9/10** and **48/50** questions. Both runs started at the first development question, so their scores overlap.

## Full-run results

The archived full runs used the same baseline extraction prompt and verifier. They cover a subset of TAT-QA where the reference number appears in a single table cell. A **strict match** requires both the reported number and scale to agree with the reference. A verifier pass means the citation passed the mechanical checks. [Dataset and selection criteria](data/manifest.json) · [Archived runs](https://github.com/KameronSB/financial-extraction-verification/tree/c64a243d39ab03d271cf7fa4080629bf73246c98/results)

| Baseline run | Strict matches / all | Verifier passes / all | Strict matches / passes |
| --- | ---: | ---: | ---: |
| Development | 216/233 (92.7%) | 233/233 (100%) | 216/233 (92.7%) |
| Original test | 194/211 (91.9%) | 208/211 (98.6%) | 194/208 (93.3%) |
| Repeat test on the same questions | 194/211 (91.9%) | 210/211 (99.5%) | 194/210 (92.4%) |

Both test runs scored **91.9%** overall. In the repeat run, 16 answers passed verification and still disagreed with the reference. Checking the cited number alone can miss a wrong year, metric, or scale. [Original test summary](https://github.com/KameronSB/financial-extraction-verification/blob/c64a243d39ab03d271cf7fa4080629bf73246c98/results/test-full.summary.json) · [Repeat test summary](https://github.com/KameronSB/financial-extraction-verification/blob/c64a243d39ab03d271cf7fa4080629bf73246c98/results/test-restored-full.summary.json)

## Reproduce a result

Score the included sample offline with Python 3.12. The evaluator prints the score and writes `results/sample.summary.json`.

```sh
python3 evaluate.py results/sample.json
```

For a live run, install the locked dependencies with `uv sync --locked --python 3.12` and set `OPENAI_API_KEY` in the environment or a local `.env` file. The saved runs used `OPENAI_MODEL=gpt-6-luna`. The prepared splits are included. This command makes one request per selected question and needs a fresh output filename.

```sh
uv run python run.py --split dev --limit 10 --out results/local/dev-run.json
uv run python evaluate.py results/local/dev-run.json
```

Use `--split test --limit 0` for all 211 test questions. The source dataset is distributed under CC BY 4.0. [TAT-QA dataset](https://github.com/NExTplusplus/TAT-QA) · [Dataset manifest](data/manifest.json)
