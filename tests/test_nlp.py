"""Unit tests for the NLP pipeline."""

from __future__ import annotations

import pytest

from smart_survey.services.nlp import (
    NLPService,
    SentimentAnalyzer,
    Summarizer,
    TopicModeler,
    normalize_text,
    split_sentences,
    tokenize,
)


@pytest.fixture()
def nlp() -> NLPService:
    return NLPService(backend="classic", max_topics=4)


class TestNormalisation:
    def test_collapses_whitespace(self):
        assert normalize_text("  hello \n\n world  ") == "hello world"

    def test_strips_urls_and_emails(self):
        cleaned = normalize_text("visit https://example.com or mail a@b.com now")
        assert "https" not in cleaned
        assert "a@b.com" not in cleaned
        assert "now" in cleaned

    def test_handles_non_string(self):
        assert normalize_text(None) == ""
        assert normalize_text(42) == ""

    def test_tokenize_lowercases_and_splits(self):
        assert tokenize("Great App, really!") == ["great", "app", "really"]

    def test_split_sentences(self):
        assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]


class TestSentiment:
    @pytest.mark.parametrize(
        "text",
        ["excellent product", "I love this app", "great support team", "very reliable and fast"],
    )
    def test_positive_texts(self, text):
        assert SentimentAnalyzer().analyze(text).label == "POSITIVE"

    @pytest.mark.parametrize(
        "text",
        ["terrible experience", "the app is broken", "awful support", "very frustrating and slow"],
    )
    def test_negative_texts(self, text):
        assert SentimentAnalyzer().analyze(text).label == "NEGATIVE"

    def test_negation_flips_polarity(self):
        analyzer = SentimentAnalyzer()
        assert analyzer.analyze("this is good").score > 0
        assert analyzer.analyze("this is not good").score < 0

    def test_intensifier_amplifies(self):
        analyzer = SentimentAnalyzer()
        assert analyzer.analyze("extremely good").score > analyzer.analyze("good").score

    def test_neutral_for_unknown_words(self):
        result = SentimentAnalyzer().analyze("the survey has questions")
        assert result.label == "NEUTRAL"
        assert result.score == 0.0

    def test_empty_text_is_neutral(self):
        assert SentimentAnalyzer().analyze("").label == "NEUTRAL"

    def test_score_is_bounded(self):
        analyzer = SentimentAnalyzer()
        for text in ["good", "excellent amazing outstanding perfect", "bad"]:
            assert -1.0 <= analyzer.analyze(text).score <= 1.0


class TestTopics:
    def test_clusters_separate_themes(self):
        texts = [
            "the export is slow and crashes",
            "exports take forever and crash",
            "pricing is too expensive for startups",
            "the price is high and costly",
            "support replies late and is rude",
            "customer support never answers",
        ]
        topics = TopicModeler(max_topics=3).model(texts)
        assert len(topics) >= 2
        assert all(topic.keywords for topic in topics)
        assert sum(topic.size for topic in topics) == len(texts)

    def test_empty_input_returns_no_topics(self):
        assert TopicModeler().model([]) == []

    def test_single_document(self):
        topics = TopicModeler().model(["only one response here"])
        assert len(topics) == 1
        assert topics[0].size == 1


class TestSummarizer:
    def test_summary_is_shorter_than_input(self):
        texts = [
            "The dashboard is fast and easy to use. Exports are quick.",
            "Support replies within an hour and is very helpful. Pricing is fair.",
            "Mobile navigation is confusing. Reporting filters are limited.",
        ]
        summary = Summarizer(max_sentences=2).summarize(texts)
        assert summary
        assert summary.count(".") <= 2

    def test_deduplicates_repeated_sentences(self):
        summary = Summarizer(max_sentences=3).summarize(["Pricing is too high."] * 5)
        assert summary.count("Pricing is too high.") == 1

    def test_empty_input(self):
        assert Summarizer().summarize([]) == ""


class TestAnalyzeTexts:
    def test_full_payload_shape(self, nlp):
        payload = nlp.analyze_texts(
            [
                "Great product, really love the dashboard",
                "Terrible support, very slow replies",
                "It is okay, nothing special",
            ]
        )
        assert payload["count"] == 3
        assert set(payload["sentiment"]) == {"POSITIVE", "NEUTRAL", "NEGATIVE"}
        assert sum(payload["sentiment"].values()) == 3
        assert payload["summary"]
        assert isinstance(payload["topics"], list)
        assert payload["keywords"]

    def test_empty_input_returns_zeroed_payload(self, nlp):
        payload = nlp.analyze_texts([])
        assert payload["count"] == 0
        assert payload["summary"] == ""
        assert payload["net_sentiment"] == 0.0

    def test_net_sentiment_is_percentage(self, nlp):
        payload = nlp.analyze_texts(["great", "terrible", "okay"])
        assert -100 <= payload["net_sentiment"] <= 100

    def test_sentiment_cache_returns_same_object(self, nlp):
        first = nlp.sentiment("great app")
        second = nlp.sentiment("  Great   APP ")
        assert first is second
