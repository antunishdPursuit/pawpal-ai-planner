"""Explicit opt-in provider evaluation; never charge the provider in normal test runs."""
import json
import os
from pathlib import Path
import pytest
from pawpal.planning.confirmation_intent import classify_confirmation

CASES = json.loads((Path(__file__).parent/'fixtures/confirmation_cases.json').read_text())


@pytest.mark.skipif(os.environ.get('PAWPAL_RUN_LIVE_INTENT') != '1', reason='Requires explicit live-provider opt-in')
@pytest.mark.parametrize('case', CASES, ids=lambda case: case['reply'])
def test_real_provider_confirmation_intent(case):
    summary = dict(owner='Demo owner', pet='Luna', title='Walk', date='2026-12-03',
                   time='10:00', timezone='America/New_York', repeat='NONE', location='Park')
    intent = classify_confirmation(case['reply'], summary, ['Overlapping task'] if case.get('conflict') else [])
    assert intent.decision == case['decision']
    if 'question_field' in case: assert intent.question_field == case['question_field']
    if 'accepts_conflict' in case: assert intent.accepts_conflict == case['accepts_conflict']
