"""Local document-type model: TF-IDF (words + character n-grams) + logistic regression.

CPU only, a few MB on disk, trains in seconds. Documents outside the configured classes are
learned explicitly as the `NEGATIVE_LABEL` class (negative examples from the training data).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion, Pipeline

NEGATIVE_LABEL = "__brak__"
ARTIFACT_VERSION = 3


def normalize_text(text: str) -> str:
    """Lowercase, no Polish diacritics: OCR often loses them ('Odwolujacy' vs 'Odwołujący')."""
    text = text.replace("ł", "l").replace("Ł", "L")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def _build_pipeline() -> Pipeline:
    features = FeatureUnion(
        [
            ("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1, max_features=60_000)),
            ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, max_features=80_000)),
        ]
    )
    classifier = LogisticRegression(C=4.0, class_weight="balanced", max_iter=2_000, random_state=42)
    return Pipeline([("features", features), ("classifier", classifier)])


@dataclass(frozen=True)
class Prediction:
    label: str | None  # None = outside the known classes
    confidence: float
    probabilities: dict[str, float]
    nearest_example: str  # id of the most similar training example (for the trace)
    nearest_similarity: float


class TextModel:
    def __init__(self, pipeline: Pipeline, example_features: Any, example_ids: list[str], meta: dict):
        self.pipeline = pipeline
        self.example_features = example_features
        self.example_ids = example_ids
        self.meta = meta

    @property
    def labels(self) -> list[str]:
        return [str(c) for c in self.pipeline.classes_]

    @classmethod
    def fit(cls, texts: list[str], labels: list[str], ids: list[str] | None = None) -> TextModel:
        if len(texts) != len(labels) or not texts:
            raise ValueError("Każdy przykład treningowy musi mieć dokładnie jedną etykietę.")
        if len(set(labels)) < 2:
            raise ValueError("Do treningu potrzebne są co najmniej dwie klasy (np. klasa + negatywy).")
        docs = [normalize_text(t) for t in texts]
        pipeline = _build_pipeline().fit(docs, labels)
        meta = {
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sklearn": sklearn.__version__,
            "examples": {label: labels.count(label) for label in sorted(set(labels))},
        }
        ids = ids or [f"{label}#{i}" for i, label in enumerate(labels)]
        return cls(pipeline, pipeline.named_steps["features"].transform(docs), ids, meta)

    def predict(self, text: str, min_confidence: float) -> Prediction:
        doc = normalize_text(text)
        proba = self.pipeline.predict_proba([doc])[0]
        best = int(np.argmax(proba))
        label, confidence = self.labels[best], float(proba[best])
        sims = cosine_similarity(self.pipeline.named_steps["features"].transform([doc]), self.example_features)[0]
        nearest = int(np.argmax(sims))
        if label == NEGATIVE_LABEL or confidence < min_confidence:
            label = None
        return Prediction(
            label=label,
            confidence=confidence,
            probabilities={lbl: round(float(p), 3) for lbl, p in zip(self.labels, proba)},
            nearest_example=self.example_ids[nearest],
            nearest_similarity=float(sims[nearest]),
        )

    def to_artifact(self) -> dict:
        return {
            "version": ARTIFACT_VERSION,
            "pipeline": self.pipeline,
            "example_features": self.example_features,
            "example_ids": self.example_ids,
            "meta": self.meta,
        }

    @classmethod
    def from_artifact(cls, artifact: dict) -> TextModel:
        if not isinstance(artifact, dict) or artifact.get("version") != ARTIFACT_VERSION:
            raise ValueError("Nieobsługiwana wersja modelu klasyfikatora - wytrenuj go ponownie (train.bat).")
        return cls(artifact["pipeline"], artifact["example_features"], artifact["example_ids"], artifact["meta"])
