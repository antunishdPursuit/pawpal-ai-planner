import pytest
from voice_completion import confirmed


@pytest.mark.parametrize('text', [
    "That sounds great to me. Let's do it.", "Yes, I confirm it.",
    "Yes, you should save it.", "Absolutely, please save the event.",
    "Sure, go ahead and save it, thank you.", "Yes, that is correct.",
    "Um, yes, please save it.", "That works for me. Go ahead.",
])
def test_natural_affirmative_replies(text):
    assert confirmed(text)


@pytest.mark.parametrize('text', [
    "Yes, but don't save it.", "No, save it tomorrow instead.",
    "Yes, change it to 9 PM.", "Don't save it", "Maybe", "Should I save it?",
    "Yes, save it if there is no conflict", "I said yes yesterday",
    "Sure, go ahead and delete it", "Save it for a different pet",
    "Yes, save it. Actually, wait.", "Yes, save it?", "Yes or no",
])
def test_mixed_negative_changed_or_uncertain_replies(text):
    assert not confirmed(text)


def test_time_conflicts_still_require_explicit_override():
    assert not confirmed("Yes, you should save it.", conflict=True)
    assert confirmed("Yes, save anyway.", conflict=True)
