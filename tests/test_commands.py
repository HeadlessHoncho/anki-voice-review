from anki_puppeteer.commands import CommandMatcher, normalize


def test_normalize_strips_punctuation_and_case():
    assert normalize("  GOOD!! ") == "good"
    assert normalize("Show.") == "show"
    assert normalize("[unk]") == "unk"


def test_exact_phrase_match():
    matcher = CommandMatcher()
    assert matcher.match("good").name == "good"
    assert matcher.match("GOOD").name == "good"
    assert matcher.match("  Easy. ").name == "easy"


def test_rejects_superstrings_and_near_misses():
    matcher = CommandMatcher()
    assert matcher.match("good job") is None
    assert matcher.match("show answer") is None
    assert matcher.match("this is good") is None
    assert matcher.match("the show") is None
    assert matcher.match("sure") is None
    assert matcher.match("heart") is None
    assert matcher.match("unk") is None
    assert matcher.match("") is None
    assert matcher.match("pizza") is None
    assert matcher.match("ah") is None
    assert matcher.match("her") is None


def test_aliases():
    matcher = CommandMatcher({"show": ("show", "show answer"), "good": ("good",)})
    assert matcher.match("show answer").name == "show"
    assert matcher.match("show").name == "show"
    assert matcher.match("good").name == "good"
