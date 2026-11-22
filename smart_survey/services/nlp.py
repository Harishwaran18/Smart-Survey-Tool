"""Deterministic, dependency-light NLP pipeline.

Two interchangeable backends sit behind :class:`NLPService`:

``classic``      TF-IDF + K-Means topics, lexicon sentiment, TextRank summaries.
                 Fast, offline and fully deterministic - the default.
``transformer``  Optional HuggingFace models for higher accuracy. Imported
                 lazily so the default install stays small.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

from smart_survey.config import get_settings
from smart_survey.logging_config import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z][a-z'\-]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

STOPWORDS: frozenset[str] = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because been
    before being below between both but by can can't cannot could couldn't did didn't do
    does doesn't doing don't down during each few for from further had hadn't has hasn't
    have haven't having he he'd he'll he's her here here's hers herself him himself his how
    how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most
    mustn't my myself no nor not of off on once only or other ought our ours ourselves out
    over own same shan't she she'd she'll she's should shouldn't so some such than that
    that's the their theirs them themselves then there there's these they they'd they'll
    they're they've this those through to too under until up very was wasn't we we'd we'll
    we're we've were weren't what what's when when's where where's which while who who's
    whom why why's with won't would wouldn't you you'd you'll you're you've your yours
    yourself yourselves also just really quite get got make made lot bit thing things
    """.split()
)

# Compact valence lexicon (-3..+3), hand-curated for survey language.
_SENTIMENT_LEXICON: dict[str, float] = {
    "excellent": 3,
    "outstanding": 3,
    "amazing": 3,
    "awesome": 3,
    "fantastic": 3,
    "superb": 3,
    "perfect": 3,
    "brilliant": 3,
    "love": 3,
    "loved": 3,
    "best": 3,
    "good": 2,
    "great": 2,
    "happy": 2,
    "pleased": 2,
    "satisfied": 2,
    "helpful": 2,
    "friendly": 2,
    "easy": 2,
    "smooth": 2,
    "fast": 2,
    "reliable": 2,
    "recommend": 2,
    "impressive": 2,
    "enjoy": 2,
    "enjoyed": 2,
    "useful": 2,
    "valuable": 2,
    "clean": 2,
    "intuitive": 2,
    "efficient": 2,
    "responsive": 2,
    "worth": 2,
    "solid": 2,
    "fine": 1,
    "ok": 1,
    "okay": 1,
    "nice": 1,
    "decent": 1,
    "pleasant": 1,
    "works": 1,
    "improved": 1,
    "better": 1,
    "like": 1,
    "liked": 1,
    "satisfying": 1,
    "polite": 1,
    "quick": 1,
    "simple": 1,
    "clear": 1,
    "stable": 1,
    "affordable": 1,
    "slow": -1,
    "confusing": -1,
    "unclear": -1,
    "difficult": -1,
    "hard": -1,
    "meh": -1,
    "average": -1,
    "expensive": -1,
    "delay": -1,
    "delayed": -1,
    "limited": -1,
    "issue": -1,
    "issues": -1,
    "annoying": -1,
    "boring": -1,
    "bad": -2,
    "poor": -2,
    "disappointed": -2,
    "disappointing": -2,
    "unhappy": -2,
    "buggy": -2,
    "bugs": -2,
    "crash": -2,
    "crashes": -2,
    "broken": -2,
    "useless": -2,
    "frustrating": -2,
    "frustrated": -2,
    "hate": -2,
    "hated": -2,
    "waste": -2,
    "unreliable": -2,
    "unhelpful": -2,
    "rude": -2,
    "problem": -2,
    "problems": -2,
    "error": -2,
    "errors": -2,
    "fail": -2,
    "failed": -2,
    "failure": -2,
    "ugly": -2,
    "terrible": -3,
    "horrible": -3,
    "awful": -3,
    "worst": -3,
    "disgusting": -3,
    "unacceptable": -3,
    "pathetic": -3,
    "nightmare": -3,
}

_NEGATIONS = frozenset(
    "not no never none nothing nobody nowhere neither nor cannot can't don't doesn't "
    "didn't isn't aren't wasn't weren't won't wouldn't shouldn't couldn't hardly barely "
    "without lack lacks lacking".split()
)

_INTENSIFIERS = {
    "very": 1.5,
    "really": 1.4,
    "extremely": 1.8,
    "incredibly": 1.7,
    "so": 1.3,
    "super": 1.6,
    "totally": 1.4,
    "absolutely": 1.7,
    "highly": 1.5,
    "quite": 1.2,
    "slightly": 0.6,
    "somewhat": 0.7,
    "barely": 0.5,
    "little": 0.7,
}

_SYNONYMS = {
    "ux": "usability",
    "ui": "usability",
    "interface": "usability",
    "app": "application",
    "apps": "application",
    "website": "site",
    "pricing": "price",
    "cost": "price",
    "costs": "price",
    "expensive": "price",
    "support": "support",
    "service": "support",
    "help": "support",
    "speed": "performance",
    "slow": "performance",
    "fast": "performance",
}


@dataclass(slots=True)
class SentimentResult:
    label: str
    score: float
    confidence: float

    def as_dict(self) -> dict[str, float | str]:
        return {"label": self.label, "score": self.score, "confidence": self.confidence}


@dataclass(slots=True)
class TopicResult:
    cluster: int
    keywords: list[str]
    size: int
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "cluster": self.cluster,
            "keywords": self.keywords,
            "size": self.size,
            "examples": self.examples,
        }


def normalize_text(text: str | None) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"\S+@\S+", " ", text)
    return re.sub(r"\s+", " ", text)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_text(text).lower())


def split_sentences(text: str) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    parts = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    return parts or [text]


def canonicalize(tokens: Iterable[str]) -> list[str]:
    return [_SYNONYMS.get(tok, tok) for tok in tokens]


class SentimentAnalyzer:
    """Lexicon sentiment with negation scope and intensifier handling."""

    def analyze(self, text: str) -> SentimentResult:
        tokens = tokenize(text)
        if not tokens:
            return SentimentResult("NEUTRAL", 0.0, 0.0)

        total = 0.0
        hits = 0
        negate_window = 0
        multiplier = 1.0

        for token in tokens:
            if token in _NEGATIONS:
                negate_window = 3
                continue
            if token in _INTENSIFIERS:
                multiplier = _INTENSIFIERS[token]
                continue
            valence = _SENTIMENT_LEXICON.get(token)
            if valence is None:
                negate_window = max(0, negate_window - 1)
                multiplier = 1.0
                continue
            value = valence * multiplier
            if negate_window > 0:
                value *= -0.8
            total += value
            hits += 1
            negate_window = max(0, negate_window - 1)
            multiplier = 1.0

        if hits == 0:
            return SentimentResult("NEUTRAL", 0.0, 0.0)

        normalized = math.tanh(total / (2.0 * math.sqrt(hits)))
        if normalized >= 0.15:
            label = "POSITIVE"
        elif normalized <= -0.15:
            label = "NEGATIVE"
        else:
            label = "NEUTRAL"
        confidence = min(0.99, 0.45 + 0.55 * abs(normalized))
        return SentimentResult(label, round(normalized, 4), round(confidence, 4))

    def analyze_many(self, texts: Sequence[str]) -> list[SentimentResult]:
        return [self.analyze(t) for t in texts]


class TopicModeler:
    """TF-IDF + K-Means topic discovery with silhouette based k selection."""

    def __init__(self, max_topics: int = 5, random_state: int = 42) -> None:
        self.max_topics = max_topics
        self.random_state = random_state

    def _vectorize(self, texts: Sequence[str]):
        vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=True
        )
        return vectorizer, vectorizer.fit_transform(texts)

    def _choose_k(self, matrix, n_samples: int) -> int:
        upper = min(self.max_topics, n_samples, max(2, int(math.sqrt(n_samples))))
        if n_samples < 4 or upper < 2:
            return 1
        best_k, best_score = 2, -1.0
        for k in range(2, upper + 1):
            labels = KMeans(n_clusters=k, random_state=self.random_state, n_init=10).fit_predict(
                matrix
            )
            if len(set(labels)) < 2:
                continue
            try:
                score = silhouette_score(matrix, labels, metric="cosine")
            except ValueError:
                continue
            if score > best_score:
                best_k, best_score = k, score
        return best_k

    def model(self, texts: Sequence[str]) -> list[TopicResult]:
        cleaned = [normalize_text(t) for t in texts]
        cleaned = [t for t in cleaned if t]
        if not cleaned:
            return []
        if len(cleaned) == 1:
            return [TopicResult(0, self._keywords(cleaned), 1, cleaned[:3])]

        vectorizer, matrix = self._vectorize(cleaned)
        k = self._choose_k(matrix, len(cleaned))
        if k <= 1:
            return [TopicResult(0, self._keywords(cleaned), len(cleaned), cleaned[:3])]

        labels = KMeans(n_clusters=k, random_state=self.random_state, n_init=10).fit_predict(matrix)
        terms = np.asarray(vectorizer.get_feature_names_out())
        topics: list[TopicResult] = []
        for cluster_id in range(k):
            idx = np.where(labels == cluster_id)[0]
            if idx.size == 0:
                continue
            weights = np.asarray(matrix[idx].mean(axis=0)).ravel()
            top = np.argsort(weights)[::-1][:8]
            topics.append(
                TopicResult(
                    cluster=int(cluster_id),
                    keywords=[terms[i] for i in top if weights[i] > 0],
                    size=int(idx.size),
                    examples=[cleaned[i][:200] for i in idx[:3]],
                )
            )
        return sorted(topics, key=lambda t: t.size, reverse=True)

    def _keywords(self, corpus: Sequence[str]) -> list[str]:
        try:
            vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            matrix = vectorizer.fit_transform(corpus)
        except ValueError:
            return []
        terms = np.asarray(vectorizer.get_feature_names_out())
        weights = np.asarray(matrix.mean(axis=0)).ravel()
        return [terms[i] for i in np.argsort(weights)[::-1][:8]]


class Summarizer:
    """Extractive TextRank summarisation (no model download required)."""

    def __init__(self, max_sentences: int = 3, damping: float = 0.85, iterations: int = 60) -> None:
        self.max_sentences = max_sentences
        self.damping = damping
        self.iterations = iterations

    def summarize(self, texts: Sequence[str], max_sentences: int | None = None) -> str:
        sentences: list[str] = []
        seen: set[str] = set()
        for text in texts:
            for sentence in split_sentences(text):
                if len(sentence.split()) < 4:
                    continue
                key = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
                if key in seen:
                    continue
                seen.add(key)
                sentences.append(sentence)
        if not sentences:
            return ""
        limit = max_sentences or self.max_sentences
        if len(sentences) <= limit:
            return " ".join(sentences)

        try:
            matrix = TfidfVectorizer(stop_words="english").fit_transform(sentences)
            similarity = cosine_similarity(matrix)
        except ValueError:
            return " ".join(sentences[:limit])

        np.fill_diagonal(similarity, 0.0)
        row_sums = similarity.sum(axis=1, keepdims=True)
        transition = np.divide(
            similarity, row_sums, out=np.zeros_like(similarity), where=row_sums != 0
        )
        scores = np.full(len(sentences), 1.0 / len(sentences))
        for _ in range(self.iterations):
            scores = (1 - self.damping) / len(sentences) + self.damping * transition.T @ scores

        chosen: list[int] = []
        for index in np.argsort(scores)[::-1]:
            if len(chosen) >= limit:
                break
            if all(similarity[index, other] < 0.8 for other in chosen):
                chosen.append(int(index))
        return " ".join(sentences[i] for i in sorted(chosen))


class KeywordExtractor:
    def extract(self, texts: Sequence[str], top_n: int = 12) -> list[tuple[str, float]]:
        corpus = [normalize_text(t) for t in texts if normalize_text(t)]
        if not corpus:
            return []
        try:
            vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
            matrix = vectorizer.fit_transform(corpus)
        except ValueError:
            return []
        terms = np.asarray(vectorizer.get_feature_names_out())
        weights = np.asarray(matrix.mean(axis=0)).ravel()
        order = np.argsort(weights)[::-1][:top_n]
        return [(terms[i], round(float(weights[i]), 5)) for i in order if weights[i] > 0]


class TransformerSentiment:
    """Optional higher-accuracy backend; the heavy import happens on first use."""

    _pipeline = None

    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-english") -> None:
        self.model_name = model_name

    def _load(self):
        if TransformerSentiment._pipeline is None:
            from transformers import pipeline  # optional dependency

            TransformerSentiment._pipeline = pipeline("sentiment-analysis", model=self.model_name)
        return TransformerSentiment._pipeline

    def analyze(self, text: str) -> SentimentResult:
        cleaned = normalize_text(text)
        if not cleaned:
            return SentimentResult("NEUTRAL", 0.0, 0.0)
        out = self._load()(cleaned, truncation=True)[0]
        score = float(out["score"])
        signed = score if out["label"].upper().startswith("POS") else -score
        label = "POSITIVE" if signed >= 0.15 else "NEGATIVE" if signed <= -0.15 else "NEUTRAL"
        return SentimentResult(label, round(signed, 4), round(score, 4))

    def analyze_many(self, texts: Sequence[str]) -> list[SentimentResult]:
        return [self.analyze(t) for t in texts]


class NLPService:
    """Facade combining sentiment, topics, keywords and summarisation."""

    def __init__(
        self,
        *,
        backend: str = "classic",
        max_topics: int = 5,
        summary_sentences: int = 3,
        cache_size: int = 256,
    ) -> None:
        self.backend = backend
        self.sentiment_analyzer = (
            TransformerSentiment() if backend == "transformer" else SentimentAnalyzer()
        )
        self.topic_modeler = TopicModeler(max_topics=max_topics)
        self.summarizer = Summarizer(max_sentences=summary_sentences)
        self.keyword_extractor = KeywordExtractor()
        self._cache: dict[str, SentimentResult] = {}
        self._cache_size = cache_size

    def sentiment(self, text: str) -> SentimentResult:
        key = normalize_text(text).lower()
        if key in self._cache:
            return self._cache[key]
        result = self.sentiment_analyzer.analyze(text)
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = result
        return result

    def analyze_texts(self, texts: Sequence[str]) -> dict[str, object]:
        """Full qualitative analysis used by the dashboard and API."""
        cleaned = [normalize_text(t) for t in texts if normalize_text(t)]
        if not cleaned:
            return {
                "count": 0,
                "sentiment": {"POSITIVE": 0, "NEUTRAL": 0, "NEGATIVE": 0},
                "average_score": 0.0,
                "net_sentiment": 0.0,
                "topics": [],
                "keywords": [],
                "summary": "",
                "highlights": {"positive": [], "negative": []},
            }

        sentiments = [self.sentiment(t) for t in cleaned]
        counts = Counter(s.label for s in sentiments)
        scores = [s.score for s in sentiments]
        positive_share = counts.get("POSITIVE", 0) / len(cleaned)
        negative_share = counts.get("NEGATIVE", 0) / len(cleaned)
        ranked = sorted(
            zip(cleaned, sentiments, strict=False), key=lambda pair: pair[1].score, reverse=True
        )

        return {
            "count": len(cleaned),
            "sentiment": {
                "POSITIVE": counts.get("POSITIVE", 0),
                "NEUTRAL": counts.get("NEUTRAL", 0),
                "NEGATIVE": counts.get("NEGATIVE", 0),
            },
            "average_score": round(float(np.mean(scores)), 4),
            "net_sentiment": round((positive_share - negative_share) * 100, 2),
            "topics": [t.as_dict() for t in self.topic_modeler.model(cleaned)],
            "keywords": [
                {"term": term, "weight": weight}
                for term, weight in self.keyword_extractor.extract(cleaned)
            ],
            "summary": self.summarizer.summarize(cleaned),
            "highlights": {
                "positive": _unique([text[:240] for text, s in ranked[:6] if s.score > 0.15]),
                "negative": _unique(
                    [text[:240] for text, s in reversed(ranked) if s.score < -0.15]
                ),
            },
        }


def _unique(items: Sequence[str], limit: int = 3) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


@lru_cache
def get_nlp_service() -> NLPService:
    settings = get_settings()
    return NLPService(
        backend=settings.nlp_backend,
        max_topics=settings.nlp_max_topics,
        summary_sentences=settings.nlp_summary_sentences,
        cache_size=settings.nlp_cache_size,
    )
