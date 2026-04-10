"""
ml_scorer.py — Local ML-based job scoring using Sentence-Transformers + MLP.

Replaces the Gemini AI filter with a fully offline model that runs instantly
and has no API quota limits.

Architecture:
  1. Sentence-Transformers (all-MiniLM-L6-v2) encodes job text → 384-dim embeddings
  2. MLPClassifier predicts relevance probability → scaled to 0-100 score
  3. Feature importance is approximated via cosine similarity to ideal profile
"""

import pickle
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple

from sentence_transformers import SentenceTransformer
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

from models import Job

logger = logging.getLogger(__name__)

MODEL_PATH = "model.pkl"
TRAIN_DATA_PATH = "train_data.csv"
EMBEDDER_NAME = "all-MiniLM-L6-v2"  # ~80MB, runs on CPU, 384-dim output

# Ideal profile description — used for cosine similarity scoring as a feature
IDEAL_PROFILE = (
    "software engineer intern co-op internship university student "
    "python react node.js pytorch tensorflow machine learning ai data science "
    "full-stack backend frontend vancouver canada remote"
)


class MLScorer:
    def __init__(self):
        logger.info(f"Loading sentence-transformer model: {EMBEDDER_NAME}...")
        self.embedder = SentenceTransformer(EMBEDDER_NAME)
        self.ideal_embedding = self.embedder.encode([IDEAL_PROFILE])[0]
        self.classifier = None
        self._load_or_train()
        logger.info("MLScorer initialized.")

    # ──────────────────────────────────────────────
    # Model lifecycle
    # ──────────────────────────────────────────────

    def _load_or_train(self):
        """Load a saved classifier or train from CSV if available."""
        if Path(MODEL_PATH).exists():
            with open(MODEL_PATH, "rb") as f:
                self.classifier = pickle.load(f)
            logger.info(f"Loaded trained MLP classifier from {MODEL_PATH}")
        elif Path(TRAIN_DATA_PATH).exists():
            self.train()
        else:
            logger.warning(
                f"No training data at {TRAIN_DATA_PATH}. "
                "Using cosine-similarity fallback scoring."
            )

    def train(self):
        """Train the MLP classifier from labeled CSV data."""
        df = pd.read_csv(TRAIN_DATA_PATH)
        if len(df) < 10:
            logger.warning(f"Only {len(df)} training samples — need at least 10. Using fallback.")
            return

        logger.info(f"Training on {len(df)} samples...")

        # Encode all training texts
        texts = df["text"].tolist()
        embeddings = self.embedder.encode(texts, show_progress_bar=True, batch_size=32)

        # Add cosine similarity to ideal profile as an extra feature
        cos_sims = np.array([
            np.dot(emb, self.ideal_embedding) / (np.linalg.norm(emb) * np.linalg.norm(self.ideal_embedding))
            for emb in embeddings
        ]).reshape(-1, 1)

        X = np.hstack([embeddings, cos_sims])
        y = df["label"].values

        self.classifier = Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPClassifier(
                hidden_layer_sizes=(128, 64),
                activation="relu",
                max_iter=500,
                early_stopping=True,
                validation_fraction=0.15,
                random_state=42,
            )),
        ])

        # Cross-validation
        n_splits = min(5, max(2, len(df) // 5))
        scores = cross_val_score(self.classifier, X, y, cv=n_splits, scoring="f1")
        logger.info(f"Cross-val F1: {scores.mean():.3f} ± {scores.std():.3f}")

        # Final fit on all data
        self.classifier.fit(X, y)

        with open(MODEL_PATH, "wb") as f:
            pickle.dump(self.classifier, f)
        logger.info(f"MLP classifier saved to {MODEL_PATH}")

    # ──────────────────────────────────────────────
    # Scoring
    # ──────────────────────────────────────────────

    def _make_text(self, job: Job) -> str:
        """Combine job fields into a single text string."""
        parts = [
            job.title or "",
            job.company or "",
            job.location or "",
            (job.description or "")[:500],
        ]
        return " ".join(parts).lower().strip()

    def _cosine_sim(self, embedding: np.ndarray) -> float:
        """Cosine similarity between a job embedding and the ideal profile."""
        dot = np.dot(embedding, self.ideal_embedding)
        norm = np.linalg.norm(embedding) * np.linalg.norm(self.ideal_embedding)
        return float(dot / norm) if norm > 0 else 0.0

    def score_job(self, job: Job) -> Job:
        """Score a single job. Sets match_score (0-100) and match_reasoning."""
        text = self._make_text(job)
        embedding = self.embedder.encode([text])[0]
        cos_sim = self._cosine_sim(embedding)

        if self.classifier is not None:
            # MLP prediction
            features = np.hstack([embedding, [cos_sim]]).reshape(1, -1)
            proba = self.classifier.predict_proba(features)[0]
            score = int(proba[1] * 100)
            method = "MLP"
        else:
            # Fallback: pure cosine similarity + keyword bonus
            score, method = self._fallback_score(job, cos_sim)

        reasoning = self._build_reasoning(job, cos_sim, score, method)

        job.match_score = score
        job.match_reasoning = reasoning
        return job

    def score_jobs(self, jobs: List[Job]) -> List[Job]:
        """Score a batch of jobs. Runs entirely locally — instant, no API calls."""
        if not jobs:
            return jobs

        logger.info(f"Scoring {len(jobs)} jobs with ML model...")

        # Batch encode for efficiency
        texts = [self._make_text(j) for j in jobs]
        embeddings = self.embedder.encode(texts, show_progress_bar=False, batch_size=32)

        for i, job in enumerate(jobs):
            cos_sim = self._cosine_sim(embeddings[i])

            if self.classifier is not None:
                features = np.hstack([embeddings[i], [cos_sim]]).reshape(1, -1)
                proba = self.classifier.predict_proba(features)[0]
                score = int(proba[1] * 100)
                method = "MLP"
            else:
                score, method = self._fallback_score(job, cos_sim)

            job.match_score = score
            job.match_reasoning = self._build_reasoning(job, cos_sim, score, method)

        scored = sum(1 for j in jobs if j.match_score and j.match_score > 80)
        logger.info(f"ML scoring complete. {scored}/{len(jobs)} jobs scored above 80.")
        return jobs

    # ──────────────────────────────────────────────
    # Fallback & Reasoning
    # ──────────────────────────────────────────────

    def _fallback_score(self, job: Job, cos_sim: float) -> Tuple[int, str]:
        """Keyword-augmented cosine similarity scoring when no trained model is available."""
        text = self._make_text(job)

        # Base score from cosine similarity (0-60 range)
        base = int(cos_sim * 60)

        # Keyword bonuses
        POSITIVE = ["intern", "co-op", "coop", "internship", "new grad",
                     "software", "data", "machine learning", "ai", "python",
                     "vancouver", "canada", "remote"]
        NEGATIVE = ["senior", "staff", "principal", "director", "10+ years",
                     "8+ years", "lead architect"]

        pos = sum(3 for kw in POSITIVE if kw in text)
        neg = sum(10 for kw in NEGATIVE if kw in text)

        score = min(100, max(0, base + pos - neg))
        return score, "Cosine+Keywords"

    def _build_reasoning(self, job: Job, cos_sim: float, score: int, method: str) -> str:
        """Build a human-readable reasoning string."""
        title_lower = (job.title or "").lower()

        signals = []

        # Level detection
        if any(w in title_lower for w in ["intern", "co-op", "coop", "internship"]):
            signals.append("✅ Intern/Co-op role")
        elif any(w in title_lower for w in ["new grad", "entry"]):
            signals.append("✅ Entry-level role")

        # Domain detection
        if any(w in title_lower for w in ["software", "developer", "engineer", "swe"]):
            signals.append("✅ Software role")
        if any(w in title_lower for w in ["data", "ml", "machine learning", "ai", "analytics"]):
            signals.append("✅ Data/ML role")

        # Location
        loc_lower = (job.location or "").lower()
        if any(w in loc_lower for w in ["vancouver", "bc", "canada"]):
            signals.append("✅ Canada-based")
        elif "remote" in loc_lower:
            signals.append("✅ Remote-friendly")

        signals.append(f"Semantic similarity: {cos_sim:.2f}")
        signals.append(f"Method: {method}")

        return " | ".join(signals)
