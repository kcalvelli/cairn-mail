"""Tests for AI classifier confidence parsing and tag normalization."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from axios_ai_mail.ai_classifier import AIClassifier, AIConfig
from axios_ai_mail.providers.base import Classification, Message


@pytest.fixture
def ai_config() -> AIConfig:
    """Create a test AI config."""
    return AIConfig(
        model="test-model",
        endpoint="http://localhost:18789",
        temperature=0.3,
    )


@pytest.fixture
def classifier(ai_config: AIConfig) -> AIClassifier:
    """Create a test classifier."""
    return AIClassifier(ai_config)


@pytest.fixture
def sample_message() -> Message:
    """Create a sample message for testing."""
    return Message(
        id="test-message-123",
        thread_id="thread-123",
        subject="Test Subject",
        from_email="sender@example.com",
        to_emails=["recipient@example.com"],
        date=datetime.now(),
        snippet="This is a test email snippet.",
        body_text="This is the full body text.",
        body_html=None,
        is_unread=True,
        has_attachments=False,
        labels=set(),
    )


class TestConfidenceParsing:
    """Tests for confidence score parsing from LLM responses."""

    def _mock_llm_response(self, classifier: AIClassifier, response_data: dict) -> Mock:
        """Helper to create a mock OpenAI-compatible API response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(response_data)}}]
        }
        mock_response.raise_for_status = Mock()
        return mock_response

    def test_valid_confidence_value(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that valid confidence values are parsed correctly."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            "confidence": 0.85,
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 0.85

    def test_missing_confidence_defaults_to_0_8(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that missing confidence defaults to 0.8."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            # No confidence field
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 0.8

    def test_confidence_clamped_to_max_1_0(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that confidence > 1.0 is clamped to 1.0."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            "confidence": 1.5,  # Out of range
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 1.0

    def test_confidence_clamped_to_min_0_0(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that confidence < 0.0 is clamped to 0.0."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            "confidence": -0.5,  # Out of range
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 0.0

    def test_invalid_confidence_type_string_defaults_to_0_8(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that invalid confidence type (string) defaults to 0.8."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            "confidence": "high",  # Invalid type
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 0.8

    def test_invalid_confidence_type_none_defaults_to_0_8(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that null confidence defaults to 0.8."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            "confidence": None,  # Explicit null
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 0.8

    def test_confidence_as_integer_is_converted(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that integer confidence is converted to float."""
        response_data = {
            "tags": ["work"],
            "priority": "normal",
            "action_required": False,
            "can_archive": False,
            "confidence": 1,  # Integer
        }

        with patch("requests.post") as mock_post:
            mock_post.return_value = self._mock_llm_response(classifier, response_data)
            result = classifier.classify(sample_message)

        assert result.confidence == 1.0
        assert isinstance(result.confidence, float)

    def test_json_parse_error_returns_low_confidence(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that JSON parse errors return classification with 0.5 confidence."""
        mock_response = Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "not valid json{{{"}}]}
        mock_response.raise_for_status = Mock()

        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_response
            result = classifier.classify(sample_message)

        assert result.confidence == 0.5
        assert result.tags == ["personal"]  # Default fallback


class TestTagNormalization:
    """Tests for tag normalization."""

    def test_tags_converted_to_lowercase(self, classifier: AIClassifier) -> None:
        """Test that tags are converted to lowercase."""
        result = classifier._normalize_tags(["WORK", "Finance", "DEV"])
        assert "work" in result
        assert "finance" in result
        assert "dev" in result

    def test_tags_stripped_of_whitespace(self, classifier: AIClassifier) -> None:
        """Test that tags are stripped of whitespace."""
        result = classifier._normalize_tags(["  work  ", "finance ", " dev"])
        assert "work" in result
        assert "finance" in result
        assert "dev" in result

    def test_duplicate_tags_removed(self, classifier: AIClassifier) -> None:
        """Test that duplicate tags are removed."""
        result = classifier._normalize_tags(["work", "Work", "WORK", "finance"])
        assert result.count("work") == 1
        assert "finance" in result

    def test_invalid_tags_filtered_out(self, classifier: AIClassifier) -> None:
        """Test that invalid tags are filtered out."""
        result = classifier._normalize_tags(["work", "invalid_tag", "unknown"])
        assert "work" in result
        assert "invalid_tag" not in result
        assert "unknown" not in result

    def test_empty_tags_defaults_to_personal(self, classifier: AIClassifier) -> None:
        """Test that empty tags list defaults to ['personal']."""
        result = classifier._normalize_tags([])
        assert result == ["personal"]

    def test_all_invalid_tags_defaults_to_personal(self, classifier: AIClassifier) -> None:
        """Test that all invalid tags defaults to ['personal']."""
        result = classifier._normalize_tags(["invalid", "unknown", "fake"])
        assert result == ["personal"]


class TestCustomTags:
    """Tests for custom tag configuration."""

    def test_custom_tags_override_defaults(self) -> None:
        """Test that custom tags override default tags."""
        custom_tags = [
            {"name": "urgent", "description": "Urgent emails"},
            {"name": "followup", "description": "Emails needing follow-up"},
        ]
        config = AIConfig(custom_tags=custom_tags)
        classifier = AIClassifier(config)

        assert classifier.tags == custom_tags
        assert classifier.tags != AIClassifier.DEFAULT_TAGS

    def test_custom_tags_used_in_normalization(self) -> None:
        """Test that custom tags are used for validation during normalization."""
        custom_tags = [
            {"name": "urgent", "description": "Urgent emails"},
            {"name": "followup", "description": "Emails needing follow-up"},
        ]
        config = AIConfig(custom_tags=custom_tags)
        classifier = AIClassifier(config)

        # Valid custom tags should pass
        result = classifier._normalize_tags(["urgent", "followup"])
        assert "urgent" in result
        assert "followup" in result

        # Default tags should be filtered out
        result = classifier._normalize_tags(["work", "finance"])
        assert result == ["personal"]  # Falls back because no valid tags

    def test_none_custom_tags_uses_defaults(self) -> None:
        """Test that None custom_tags uses default tags."""
        config = AIConfig(custom_tags=None)
        classifier = AIClassifier(config)

        assert classifier.tags == AIClassifier.DEFAULT_TAGS


class TestClassificationResult:
    """Tests for classification result structure."""

    def test_classification_has_all_required_fields(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that classification result has all required fields."""
        response_data = {
            "tags": ["work", "dev"],
            "priority": "high",
            "action_required": True,
            "can_archive": False,
            "confidence": 0.9,
        }

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"choices": [{"message": {"content": json.dumps(response_data)}}]}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            result = classifier.classify(sample_message)

        assert isinstance(result, Classification)
        assert result.tags == ["work", "dev"]
        assert result.priority == "high"
        assert result.todo is True
        assert result.can_archive is False
        assert result.confidence == 0.9

    def test_invalid_priority_defaults_to_normal(
        self, classifier: AIClassifier, sample_message: Message
    ) -> None:
        """Test that invalid priority values default to 'normal'."""
        response_data = {
            "tags": ["work"],
            "priority": "urgent",  # Invalid
            "action_required": False,
            "can_archive": False,
            "confidence": 0.8,
        }

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"choices": [{"message": {"content": json.dumps(response_data)}}]}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            result = classifier.classify(sample_message)

        assert result.priority == "normal"
