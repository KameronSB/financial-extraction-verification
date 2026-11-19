# How did $2.55 per share become $2.55 million?

American Tower’s pro forma financial table puts 2018 basic net income at **$2.55 per common share**. My extractor found the right year, selected the right row, and copied `$2.55` exactly. It also returned `million` as the scale. My verifier accepted the answer and recorded a normalised value of `2550000.00`. [Source table](../results/test-full.json#L21124) · [Saved prediction](../results/test-full.json#L21166)

The table contains a clue to how that could happen. A note says the amounts are in millions unless otherwise disclosed. A heading immediately above the cell introduces the per-share figures. The citation points to the number. To establish its unit, a reader also needs that heading. [Table heading and note](../results/test-full.json#L21124)

## What a cell citation can establish

I built a Python pipeline to see how many extraction errors a simple check could catch. I selected questions from TAT-QA whose numeric reference appears in a table cell. GPT-6 Luna received the question, the indexed table, and the surrounding paragraphs. It returned a value, scale, row, and column, or indicated that it could find no answer. Python looked up the coordinates and compared the numbers. A separate evaluator scored the reported value and scale against the reference. [Selection rules](../prepare_data.py#L35) · [Extraction prompt](../extract.py#L20) · [Cell checks](../verify.py#L21) · [Scoring rule](../evaluate.py#L54)

On 211 held-out questions, 194 answers matched the reference (91.9%). Three cases were flagged for review. The model abstained twice, and once it returned `2019` while citing a cell containing `2014`. Of the 208 answers that passed, 14 disagreed with the reference. Ten of those 14 matched the reference value and differed only on scale, including the American Tower example. [Test summary and example IDs](../results/test-full.summary.json#L5) · [Rejected citation](../results/test-full.json#L9167)

Looking at the source also changed how I read those 14 disagreements. One question asks for issued and paid-up capital in 2019. The model selected 83,692 from the 2019 column. The reference expects 66,128, the figure in the adjacent 2018 column. I kept the disagreement in the published score so readers can reproduce it and inspect the evidence themselves. [Question and table](../results/test-full.json#L4389) · [Reference and prediction](../results/test-full.json#L4464)

The next experiment I’d run is to ask the model to cite the heading or note that supports its chosen scale. For the $2.55 answer, a citation to the general note would prompt a reviewer to look for the exception above the row. I’d design the check on development data, then count both the scale disagreements it catches and the reference-matching answers it sends to review on fresh examples.
