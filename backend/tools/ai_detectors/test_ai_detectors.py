import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # tools dir

import pytest
from ai_detectors.detector import AIDetector, PowerfulAIDetector
from ai_detectors import PowerfulAIDetector as PD
from ai_detectors.engines.base import TextContext, clamp
from ai_detectors.engines import ALL_ENGINES


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def detector():
    return PowerfulAIDetector()


@pytest.fixture
def ai_slop_text():
    return (
        "In conclusion, it is important to note that leveraging robust frameworks "
        "can foster a holistic paradigm. Furthermore, this multifaceted approach "
        "underscores the comprehensive synergy. Moreover, it is crucial to delve "
        "into the ever-evolving landscape. Ultimately, this serves as a testament "
        "to the cutting-edge, game-changing innovation."
    )


@pytest.fixture
def human_text():
    return (
        "I don't really get why people oversimplify this stuff. yeah it's complicated, "
        "but that's what makes it interesting, right? I've been poking around the data "
        "for weeks and honestly some of it just doesn't add up. Could be a measurement "
        "error, could be something real — dunno yet. The thing is, nobody bothered to "
        "check the underlying assumptions before publishing. kind of wild if you ask me. "
        "We should probably rerun those tests with a larger sample."
    )


# ── 1. Empty text ────────────────────────────────────────────────────────────

class TestEmptyText:

    def test_empty_string(self, detector):
        score, details = detector.analyze('')
        assert score == 0.0
        assert 'verdict' in details

    def test_whitespace_only(self, detector):
        score, details = detector.analyze('   ')
        assert score == 0.0 or (0 <= score <= 100)
        assert 'verdict' in details


# ── 2. Score range ───────────────────────────────────────────────────────────

class TestScoreRange:

    @pytest.mark.parametrize("text", [
        "Short text.",
        "This is a normal paragraph with some words in it. Nothing special here.",
        "In conclusion, leveraging robust frameworks fosters a holistic paradigm. "
        "Furthermore, this multifaceted approach underscores synergy.",
        "I don't know what to think. yeah, it's weird but maybe it works. "
        "We'll see what happens next, I guess.",
    ])
    def test_score_in_range(self, detector, text):
        score, details = detector.analyze(text)
        assert 0 <= score <= 100, f"Score {score} out of range for text: {text[:50]}..."
        assert 'verdict' in details


# ── 3. AI slop high ──────────────────────────────────────────────────────────

class TestAISlopHigh:

    def test_ai_slop_score(self, detector, ai_slop_text):
        score, details = detector.analyze(ai_slop_text)
        assert score > 50, f"AI slop score {score} should be > 50"
        assert 'verdict' in details


# ── 4. Human low ─────────────────────────────────────────────────────────────

class TestHumanLow:

    def test_human_low_score(self, detector, human_text, ai_slop_text):
        score_human, _ = detector.analyze(human_text)
        score_ai, _ = detector.analyze(ai_slop_text)
        assert score_human < score_ai, (
            f"Human score {score_human} should be < AI score {score_ai}"
        )


# ── 5. Backward compat keys ──────────────────────────────────────────────────

class TestBackwardCompatKeys:

    def test_backward_compat_keys(self, detector, ai_slop_text):
        _, details = detector.analyze(ai_slop_text)
        assert 'final_score' in details
        assert 'verdict' in details
        compat_keys = [
            'slop_density', 'burstiness', 'perplexity_approx',
            'repetition', 'vocabulary_richness', 'starter_pattern',
        ]
        for key in compat_keys:
            assert key in details, f"Missing compat key: {key}"


# ── 6. Engines keys ──────────────────────────────────────────────────────────

class TestEnginesKeys:

    def test_engines_dict_present(self, detector, ai_slop_text):
        _, details = detector.analyze(ai_slop_text)
        assert 'engines' in details
        engines = details['engines']
        assert isinstance(engines, dict)
        for eng_cls in ALL_ENGINES:
            assert eng_cls.name in engines, f"Engine {eng_cls.name} missing from details"
            eng_data = engines[eng_cls.name]
            assert 'score' in eng_data
            assert 'weight' in eng_data
            assert 0 <= eng_data['score'] <= 1 or eng_cls.name == 'human_signal', (
                f"Engine {eng_cls.name} score {eng_data['score']} out of [0,1]"
            )


# ── 7. All engines run ──────────────────────────────────────────────────────

class TestAllEnginesRun:

    def test_all_engines_produce_floats(self):
        text = (
            "In conclusion, it is important to note that leveraging robust frameworks "
            "can foster a holistic paradigm. Furthermore, this multifaceted approach "
            "underscores the comprehensive synergy. Moreover, it is crucial to delve "
            "into the ever-evolving landscape. Ultimately, this serves as a testament "
            "to the cutting-edge, game-changing innovation."
        )
        ctx = TextContext(text)
        for eng_cls in ALL_ENGINES:
            engine = eng_cls()
            result = engine.analyze(ctx)
            assert isinstance(result, float), (
                f"Engine {engine.name} returned {type(result)}, expected float"
            )
            if engine.name == "human_signal":
                assert -0.15 <= result <= 0.10, (
                    f"Engine {engine.name} result {result} out of [-0.15, 0.10]"
                )
            else:
                assert 0.0 <= result <= 1.0, (
                    f"Engine {engine.name} result {result} out of [0, 1]"
                )


# ── 8. Robustness ────────────────────────────────────────────────────────────

class TestRobustness:

    @pytest.mark.parametrize("text", [
        "123 456",
        "hello",
        "こんにちは世界 🌍🎉 你好",
    ])
    def test_no_exception(self, detector, text):
        score, details = detector.analyze(text)
        assert 0 <= score <= 100
        assert isinstance(details, dict)

    def test_very_long_text(self, detector):
        words = ["word" + str(i % 200) for i in range(5000)]
        text = " ".join(words)
        score, details = detector.analyze(text)
        assert 0 <= score <= 100
        assert 'verdict' in details


# ── 9. Attributed model ──────────────────────────────────────────────────────

class TestAttributedModel:

    def test_attributed_model_key(self, detector, ai_slop_text):
        _, details = detector.analyze(ai_slop_text)
        assert 'attributed_model' in details
        assert details['attributed_model'] is None or isinstance(details['attributed_model'], str)

    def test_human_text_attributed_model(self, detector, human_text):
        _, details = detector.analyze(human_text)
        assert 'attributed_model' in details
        assert details['attributed_model'] is None or isinstance(details['attributed_model'], str)


# ── 10. Determinism ──────────────────────────────────────────────────────────

class TestDeterminism:

    def test_deterministic(self, detector, ai_slop_text):
        score1, _ = detector.analyze(ai_slop_text)
        score2, _ = detector.analyze(ai_slop_text)
        assert score1 == score2, f"Non-deterministic: {score1} vs {score2}"

    def test_deterministic_human(self, detector, human_text):
        score1, _ = detector.analyze(human_text)
        score2, _ = detector.analyze(human_text)
        assert score1 == score2, f"Non-deterministic: {score1} vs {score2}"
