"""Tests for the intent detector."""

from app.ai.intent_detector import detect_intent, extract_target, Intent, IntentDetector


class TestDetectIntent:
    def test_explain_repository(self):
        assert detect_intent("Explain this repository") == Intent.EXPLAIN_REPOSITORY
        assert detect_intent("Give me an overview of the project") == Intent.EXPLAIN_REPOSITORY

    def test_explain_file(self):
        assert detect_intent("Explain this file") == Intent.EXPLAIN_FILE
        assert detect_intent("What does this file do?") == Intent.EXPLAIN_FILE

    def test_explain_class(self):
        assert detect_intent("Explain this class") == Intent.EXPLAIN_CLASS
        assert detect_intent("class overview DatabaseManager") == Intent.EXPLAIN_CLASS

    def test_explain_function(self):
        assert detect_intent("Explain this function") == Intent.EXPLAIN_FUNCTION
        assert detect_intent("how does this function work") == Intent.EXPLAIN_FUNCTION

    def test_review_code(self):
        assert detect_intent("Review this code") == Intent.REVIEW_CODE
        assert detect_intent("Code review the authentication module") == Intent.REVIEW_CODE

    def test_find_usage(self):
        assert detect_intent("Where is connect used?") == Intent.FIND_USAGE
        assert detect_intent("references to UserService") == Intent.FIND_USAGE

    def test_find_implementation(self):
        assert detect_intent("where is DatabaseManager defined") == Intent.FIND_IMPLEMENTATION
        assert detect_intent("find definition of connect") == Intent.FIND_IMPLEMENTATION

    def test_architecture(self):
        assert detect_intent("architecture of this project") == Intent.ARCHITECTURE
        assert detect_intent("component diagram") == Intent.ARCHITECTURE

    def test_general_question(self):
        assert detect_intent("Hello") == Intent.GENERAL_QUESTION
        assert detect_intent("What is Python?") == Intent.GENERAL_QUESTION
        assert detect_intent("explain DatabaseManager") == Intent.GENERAL_QUESTION


class TestExtractTarget:
    def test_explain_prefix(self):
        assert extract_target("explain DatabaseManager") == "DatabaseManager"
        assert extract_target("explain connect()") == "connect"

    def test_where_is(self):
        assert extract_target("where is connect used?") == "connect"

    def test_review(self):
        assert extract_target("review utils.py") == "utils.py"

    def test_no_target(self):
        assert extract_target("Hello") is None
        assert extract_target("What is this?") is None

    def test_capitalized_fallback(self):
        assert extract_target("What does DatabaseManager do?") == "DatabaseManager"

    def test_snake_case_fallback(self):
        assert extract_target("find connect_to_db") == "connect_to_db"

    def test_this_bookended(self):
        assert extract_target("review this code") is None


class TestIntentDetectorClass:
    def test_detect_returns_tuple(self):
        detector = IntentDetector()
        intent, target = detector.detect("Explain this repository")
        assert intent == Intent.EXPLAIN_REPOSITORY
        assert target is None

    def test_detect_with_target(self):
        detector = IntentDetector()
        intent, target = detector.detect("explain DatabaseManager")
        assert intent == Intent.GENERAL_QUESTION
        assert target == "DatabaseManager"

    def test_detect_where_is(self):
        detector = IntentDetector()
        intent, target = detector.detect("where is connect used?")
        assert intent == Intent.FIND_USAGE
        assert target == "connect"
