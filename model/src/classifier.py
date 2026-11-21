from __future__ import annotations

from dataclasses import dataclass
import math
from collections import Counter
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion, Pipeline


UNSUPPORTED_LABEL = "__unsupported__"
DEFAULT_MIN_CONFIDENCE = 0.55
DEFAULT_MIN_SIMILARITY = 0.18
SIMILARITY_PERCENTILE = 0.05


@dataclass(frozen=True)
class Classification:
    document_type: str | None
    confidence: float
    nearest_example_similarity: float
    status: str


def build_model() -> Pipeline:
    features = FeatureUnion(
        [
            (
                "words",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                    max_features=80_000,
                ),
            ),
            (
                "characters",
                TfidfVectorizer(
                    analyzer="char_wb",
                    lowercase=True,
                    ngram_range=(3, 5),
                    sublinear_tf=True,
                    max_features=120_000,
                ),
            ),
        ]
    )
    return Pipeline(
        [
            ("features", features),
            (
                "classifier",
                LogisticRegression(
                    C=4.0,
                    class_weight="balanced",
                    max_iter=2_000,
                    random_state=42,
                ),
            ),
        ]
    )


class DocumentClassifier:
    def __init__(
        self,
        model: Pipeline,
        exemplar_features: Any,
        exemplar_labels: list[str],
        min_similarity_by_label: dict[str, float],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
            raise ValueError("Minimum confidence must be between 0 and 1.")
        self.model = model
        self.exemplar_features = exemplar_features
        self.exemplar_labels = np.asarray(exemplar_labels)
        self.min_similarity_by_label = min_similarity_by_label
        self.min_confidence = min_confidence

    @classmethod
    def fit(
        cls,
        texts: list[str],
        labels: list[str],
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> DocumentClassifier:
        if len(texts) != len(labels):
            raise ValueError("Each training text must have exactly one label.")
        if not labels or any(not label.strip() for label in labels):
            raise ValueError("Training labels must not be empty.")
        if len(set(labels)) < 2:
            raise ValueError("At least two document types are required for training.")
        if not texts or any(not text.strip() for text in texts):
            raise ValueError("Training texts must not be empty.")
        class_counts = Counter(labels)
        if any(count < 2 for count in class_counts.values()):
            raise ValueError(
                "At least two examples per document type are required to calibrate "
                "unknown-document rejection."
            )

        model = build_model()
        model.fit(texts, labels)
        exemplar_features = model.named_steps["features"].transform(texts)
        leave_one_out_similarities = cosine_similarity(exemplar_features)
        np.fill_diagonal(leave_one_out_similarities, -1.0)
        exemplar_labels = np.asarray(labels)
        min_similarity_by_label = {}
        for label in class_counts:
            class_indexes = np.flatnonzero(exemplar_labels == label)
            class_similarities = leave_one_out_similarities[
                np.ix_(class_indexes, class_indexes)
            ]
            nearest_similarities = class_similarities.max(axis=1)
            min_similarity_by_label[label] = max(
                DEFAULT_MIN_SIMILARITY,
                float(np.quantile(nearest_similarities, SIMILARITY_PERCENTILE)),
            )
        return cls(
            model,
            exemplar_features,
            labels,
            min_similarity_by_label,
            min_confidence,
        )

    def classify(self, text: str) -> Classification:
        if not text.strip():
            raise ValueError("Document text must not be empty.")
        probabilities = self.model.predict_proba([text])[0]
        best_index = probabilities.argmax()
        confidence = float(probabilities[best_index])
        predicted_label = str(self.model.classes_[best_index])

        query_features = self.model.named_steps["features"].transform([text])
        matching_exemplars = self.exemplar_labels == predicted_label
        nearest_example_similarity = float(
            cosine_similarity(
                query_features, self.exemplar_features[matching_exemplars]
            ).max()
        )

        if (
            confidence < self.min_confidence
            or nearest_example_similarity
            < self.min_similarity_by_label[predicted_label]
        ):
            return Classification(
                None,
                confidence,
                nearest_example_similarity,
                "uncertain",
            )
        if predicted_label == UNSUPPORTED_LABEL:
            return Classification(
                None,
                confidence,
                nearest_example_similarity,
                "unsupported",
            )
        return Classification(
            predicted_label,
            confidence,
            nearest_example_similarity,
            "classified",
        )

    def to_artifact(self) -> dict[str, Any]:
        return {
            "version": 2,
            "min_confidence": self.min_confidence,
            "model": self.model,
            "exemplar_features": self.exemplar_features,
            "exemplar_labels": self.exemplar_labels.tolist(),
            "min_similarity_by_label": self.min_similarity_by_label,
        }

    @classmethod
    def from_artifact(cls, artifact: dict[str, Any]) -> DocumentClassifier:
        if artifact.get("version") != 2:
            raise ValueError("Unsupported or invalid classifier artifact version.")
        model = artifact.get("model")
        if not isinstance(model, Pipeline) or not hasattr(model, "classes_"):
            raise ValueError("Classifier artifact does not contain a trained model.")
        exemplar_features = artifact.get("exemplar_features")
        exemplar_labels = artifact.get("exemplar_labels")
        min_similarity_by_label = artifact.get("min_similarity_by_label")
        if (
            exemplar_features is None
            or not isinstance(exemplar_labels, list)
            or not isinstance(min_similarity_by_label, dict)
        ):
            raise ValueError("Classifier artifact is missing unknown-rejection data.")
        min_confidence = artifact.get("min_confidence")
        if not isinstance(min_confidence, (int, float)):
            raise ValueError("Classifier artifact does not contain a valid confidence.")
        return cls(
            model,
            exemplar_features,
            exemplar_labels,
            {str(label): float(score) for label, score in min_similarity_by_label.items()},
            float(min_confidence),
        )
