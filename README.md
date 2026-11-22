# Financial table extraction and verification

This project uses GPT-6 Luna to answer financial questions from TAT-QA tables and accompanying text. Each answer includes a number, its reporting scale, and the source cell. Python checks that the number agrees with the cited cell. The evaluator then compares the number and scale with the reference answer. [Extraction](extract.py) · [Verification](verify.py) · [Evaluation](evaluate.py)

Write for this repo is found on my [blog here](https://kameronbains.com/posts/building-a-financial-extraction-system-with-llms-and-python)

## Worked result

For **“What is the amount of total sales in 2019?”**, the model returned **$1,496.5 million**. It selected the “Total sales” row under the 2019 heading, at zero-based row 4, column 1. The cell contains `$1,496.5`, and the table introduction specifies millions. The answer passed verification and matched the reference on both number and scale. [Sample run](results/sample.json) · [Score](results/sample.summary.json)

Two smaller development runs matched the number and scale on **9/10** and **48/50** questions. Both started at the first development question, so their scores overlap. [10 predictions](results/dev-10.json) · [10-question summary](results/dev-10.summary.json) · [50 predictions](results/dev-50.json) · [50-question summary](results/dev-50.summary.json)

## Full-run results

The full runs used the same baseline extraction prompt and verifier. They cover a subset of TAT-QA where the reference number appears in a single table cell. A **strict match** requires both the reported number and scale to agree with the reference. A verifier pass means the citation passed the mechanical checks. [Dataset and selection criteria](data/manifest.json)

| Baseline run | Strict matches / all | Verifier passes / all | Strict matches / passes | Saved results |
| --- | ---: | ---: | ---: | --- |
| Development | 216/233 (92.7%) | 233/233 (100%) | 216/233 (92.7%) | [Predictions](results/dev-full.json) · [Summary](results/dev-full.summary.json) |
| Original test | 194/211 (91.9%) | 208/211 (98.6%) | 194/208 (93.3%) | [Predictions](results/test-full.json) · [Summary](results/test-full.summary.json) |
| Repeat test on the same questions | 194/211 (91.9%) | 210/211 (99.5%) | 194/210 (92.4%) | [Predictions](results/test-restored-full.json) · [Summary](results/test-restored-full.summary.json) |

Both test runs scored **91.9%** overall. In the repeat run, 16 answers passed verification and still disagreed with the reference. Checking the cited number alone can miss a wrong year, metric, or scale.

## Reproduce a result

Score any saved run offline with Python 3.12. The evaluator prints the score and writes the corresponding `.summary.json` beside the predictions.

```sh
python3 evaluate.py results/sample.json
python3 evaluate.py results/test-restored-full.json
```

For a live run, install the locked dependencies with `uv sync --locked --python 3.12` and set `OPENAI_API_KEY` in the environment or a local `.env` file. The saved runs used `OPENAI_MODEL=gpt-6-luna`. The prepared splits are included. This command makes one request per selected question and needs a fresh output filename.

```sh
uv run python run.py --split dev --limit 10 --out results/local/dev-run.json
uv run python evaluate.py results/local/dev-run.json
```

Use `--split test --limit 0` for all 211 test questions. The source dataset is distributed under CC BY 4.0. [TAT-QA dataset](https://github.com/NExTplusplus/TAT-QA) · [Dataset manifest](data/manifest.json)
