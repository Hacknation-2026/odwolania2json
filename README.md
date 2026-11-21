# odwolania2json
Urząd Zamówień Publicznych - Odwołania2JSON

## Train the document classifier

The classifier learns document types from the PDF text and paired JSON labels.
It uses word and character TF-IDF features with logistic regression, which can
be trained locally on the provided small dataset. PDF filenames are not model
features. An empty `{}` annotation is learned as an unsupported-document
example. Predictions also need to be sufficiently similar to a labeled training
example of the predicted class; this lets the classifier reject unrelated
documents even when its probability for one known class is high. Low-confidence
or dissimilar predictions are returned as uncertain instead of forcing a type.

Install dependencies and build the case-wise dataset splits. The default split
randomly assigns 40 of the 60 case folders to training, 10 to validation, and
10 to testing; all PDFs from a case stay together:

```bash
python -m pip install -r requirements.txt
python model/src/build_dataset.py
```

Train using only the training split, then report metrics separately for
validation and test:

```bash
python model/src/train.py
```

Classify PDFs and convert each recognized document to its matching JSON schema:

```bash
python model/src/predict.py input/example.pdf
python model/src/predict.py input/
```

JSON files are written to `output/`, preserving the directory structure under
the input folder and using the same basename as each PDF. For example,
`input/case1/document.pdf` produces `output/case1/document.json`. Override the
destination with `--output-dir path/to/output`. Documents classified as
unsupported or uncertain produce an empty `{}` JSON object.

The trained classifier identifies the document type from its text. A local,
deterministic extractor then fills the corresponding fields for odwołania,
pełnomocnictwa, and transfer confirmations; no external model API is used.
The CLI prints one JSON Lines status record per PDF, including its type,
confidence, and output path. The classifier artifact is saved to
`model/models/document_classifier.joblib`. PDFs without selectable text require
OCR before processing.

## Build PDF-to-JSON training data

The converter extracts selectable text from labeled PDFs and creates JSONL
training examples. Each PDF must have its matching JSON file beside it. A payment confirmation PDF named
`potwierdzenie_przelewu.pdf` is paired with `przelew.json`.

Put each case in its own folder under `model/data/raw/`, for example:

```text
model/data/raw/przyklad_01/
  odwolanie.pdf
  odwolanie.json
  pelnomocnictwo.pdf
  pelnomocnictwo.json
  potwierdzenie_przelewu.pdf
  przelew.json
```

Run the converter from the repository root:

```bash
model/.venv/bin/python model/src/build_dataset.py
```

To use PDFs stored elsewhere, pass their parent directory explicitly:

```bash
model/.venv/bin/python model/src/build_dataset.py --input-dir Model/Data
```

The converter writes `train.jsonl`, `validation.jsonl`, and `test.jsonl` under
`model/data/processed/`. The default ratios are 40/10/10 case folders for the
60-folder dataset. The random assignment uses seed 42 and can be changed with
`--seed`; ratios can be overridden with `--validation-ratio` and
`--test-ratio`. All documents from a case stay in the same split.
Scanned PDFs without selectable text need OCR before conversion.
