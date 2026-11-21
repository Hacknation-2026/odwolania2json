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
Similarity thresholds are calibrated across different base cases, so augmented
versions of one case do not inflate the rejection threshold.

Install dependencies and build the case-wise dataset splits. The default split
randomly assigns 40 of the 60 base cases to training, 10 to validation, and 10
to testing. Each split includes 5% of its available augmented folders: 4 of 80
for training and 1 of 20 for each held-out split. The selected augmented
folder is kept with its base case:

```bash
python -m pip install -r requirements.txt
python model/src/build_dataset.py
```

Train using only the training split, then report metrics separately for
validation and test:

```bash
python model/src/train.py
```

Classify PDFs and convert each recognized document to its matching JSON schema.
Put the PDFs (for example one folder per case) in `input/` and run:

```bash
start.bat                              # Windows: creates .venv, installs requirements, processes input/
python model/src/predict.py            # same, without the wrapper
python model/src/predict.py input/example.pdf
```

Every run starts by clearing earlier results from `output/`, so afterwards
`output/` mirrors exactly the PDFs currently in `input/` (`--keep-output` turns
this off; a custom `--output-dir` is never cleared). `input/` is never modified.

JSON files are written to `output/`, preserving the directory structure under
the input folder and using the same basename as each PDF. For example,
`input/case1/document.pdf` produces `output/case1/document.json`. Override the
destination with `--output-dir path/to/output`. Documents classified as
unsupported or uncertain, and PDFs that cannot be read, produce an empty `.json`
file; one bad PDF does not stop the rest of the batch.

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

Put each base case and its augmented variants in separate folders under
`model/data/raw_augmented/`, for example:

```text
model/data/raw_augmented/przyklad_01/
  odwolanie.pdf
  odwolanie.json
  pelnomocnictwo.pdf
  pelnomocnictwo.json
  potwierdzenie_przelewu.pdf
  przelew.json
model/data/raw_augmented/przyklad_01_aug1/
  ...
model/data/raw_augmented/przyklad_01_aug2/
  ...
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
`model/data/processed/`. The default split produces 132 training examples and
33 examples each for validation and test. Augmented folders are sampled
separately within each split, while their base case families never cross
splits. The augmentation fraction can be changed with `--augmentation-ratio`
(default `0.05`). The random assignment uses seed 42 and can be changed with
`--seed`; case ratios can be overridden with `--validation-ratio` and
`--test-ratio`.
Scanned PDFs without selectable text need OCR before conversion.

## Data Augmentation for Scanned Documents

To expand the training set from the initial 150 documents and prevent overfitting to clean, synthetic PDF layouts, a realistic scanner degradation engine is provided in `model/src/augment.py`. It converts pristine PDFs into degraded scanned PDF representations while preserving paired JSON annotations.

### Degradation Effects

- **Photometric Variations**: Brightness scaling (underexposed/dark to washed out), low/high contrast, uneven lighting and shadow gradients (scanner lid gaps, hand/mobile shadows).
- **Geometric & Orientation Distortions**: 180° page flips (common in Automatic Document Feeder scans), 90°/270° orientation mismatch, slight skew angles (±0.5° to ±4°).
- **Physical & Sensor Artifacts**: Salt-and-pepper noise (dust on glass platen), vertical scanner slit streaks, Gaussian defocus blur, paper background tinting, and JPEG compression artifacts.
- **Searchable PDF Compliance**: Input is `.pdf` and output remains a valid `.pdf` embedding a searchable text layer and optional simulated OCR misreadings.

### Usage

Augment a single PDF:

```bash
model/.venv/bin/python model/src/augment.py --input-file model/data/raw/przyklad_01/odwolanie.pdf --output distorted.pdf
```

Augment a single case folder:

```bash
model/.venv/bin/python model/src/augment.py --case-dir model/data/raw/przyklad_01 --output-dir model/data/raw/przyklad_01_aug1
```

Augment the entire dataset (creates augmented variants `przyklad_XX_aug1`, `przyklad_XX_aug2`, etc.):

```bash
model/.venv/bin/python model/src/augment.py --dataset-dir model/data/raw --output-dir model/data/raw_augmented --copies 2 --preset realistic
```

Then rebuild the dataset splits from the augmented data:

```bash
model/.venv/bin/python model/src/build_dataset.py --input-dir model/data/raw_augmented
model/.venv/bin/python model/src/train.py
```

