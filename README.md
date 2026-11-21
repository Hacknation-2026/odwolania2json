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

Install dependencies and build the case-wise dataset splits:

```bash
python -m pip install -r requirements.txt
python model/src/build_dataset.py
```

Train and evaluate the model on the held-out test split:

```bash
python model/src/train.py
```

Classify a PDF or recursively classify all PDFs in a folder:

```bash
python model/src/predict.py input/example.pdf
python model/src/predict.py input/
```

The classifier artifact is saved to `model/models/document_classifier.joblib`.
Predictions are printed as JSON Lines with the document type, confidence,
similarity to the nearest labeled example, and status (`classified`,
`unsupported`, or `uncertain`).

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
`model/data/processed/`. All documents from a case stay in the same split.
Scanned PDFs without selectable text need OCR before conversion.
