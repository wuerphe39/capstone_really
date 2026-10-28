from ..services.care import audio_lead, with_audio_lead

NONE = {'analyzed_windows': 1, 'dog_candidate_windows': 0}
SOME = {'analyzed_windows': 2, 'dog_candidate_windows': 1}
GEMINI_NONE = ('현재 음성 분석에서 짖음 후보는 발견되지 않았습니다. 소리 크기 변화만으로는 짖음을 확정할 수 없으므로, '
               '보호자께서는 관찰 원본 소리를 다시 확인하시고 주변 자극이나 반려견의 상태를 살펴봐 주시기 바랍니다.')
GEMINI_SOME = ('최근 관찰 기록과 음성 분석 결과, 짖음 후보가 일부 감지되었으나 실제 짖음으로 확정할 수는 없습니다. '
               '후보 구간의 원본 소리와 전후 영상을 확인해 주세요.')


def test_no_candidate_is_not_worded_as_no_bark():
    text = with_audio_lead(GEMINI_NONE, NONE)
    assert text.startswith('이 구간에서는 모델이 짖음 점수를 기준 이상으로 내지 않았습니다')
    assert '짖음이 없었다는 뜻은 아닙니다' in text
    assert '발견되지 않았습니다' not in text
    assert '원본 소리를 다시 확인하시고' in text  # the provider's advice is kept


def test_candidate_is_stated_first_and_still_needs_the_guardian():
    text = with_audio_lead(GEMINI_SOME, SOME)
    assert text.startswith('개 짖음 소리 후보가 감지되었습니다(분석 창 2개 중 1개)')
    assert '보호자가 원본을 듣고 확인' in text
    assert '확정할 수는 없습니다' not in text  # no second, vaguer restatement
    assert '후보 구간의 원본 소리와 전후 영상을 확인해 주세요.' in text


def test_a_summary_made_only_of_restatements_becomes_the_lead():
    assert with_audio_lead('짖음 후보는 발견되지 않았습니다.', NONE) == audio_lead(NONE)


def test_loudness_rates_and_empty_conditionals_are_not_repeated():
    text = with_audio_lead('분당 빈도 기준으로 최근 기록에서 12.0~24.0회 수준의 소리가 확인되었습니다. '
                           '후보가 있어도 실제 반려견의 짖음으로 확정할 수 없으므로 원본 재청취를 제안합니다. '
                           '원본을 다시 들어 주세요.', NONE)
    assert '12.0' not in text and '후보가 있어도' not in text
    assert text.endswith('원본을 다시 들어 주세요.')


def test_decimal_per_minute_values_and_the_echoed_caution_are_dropped():
    text = with_audio_lead('인용된 기록에 따르면 분당 24.04회(ID: 64), 분당 12.00회(ID: 63) 등의 빈도 값이 확인됩니다. 원본을 들어 주세요.', NONE)
    assert '24.04' not in text and text.endswith('원본을 들어 주세요.')
    text = with_audio_lead('후보가 있어도 실제 반려견의 짖음으로 확정하지 않으므로 원본 재청취를 제안합니다. 전후 장면을 확인해 주세요.', SOME)
    assert '후보가 있어도' not in text and text.endswith('전후 장면을 확인해 주세요.')


PAST = '이번 외출은 분석 창 1개 중 개 짖음 후보 창 1개, 이전 외출은 분석 창 1개 중 1개입니다. 외출 길이와 환경이 달라 평소 패턴과 비교한 것이 아닙니다.'


def test_denying_earlier_records_is_replaced_by_the_servers_comparison_sentence():
    from ..services.care import past_comparison_fact
    text = with_audio_lead('이전 외출이나 비교할 과거 기록이 없어 비교 근거가 부족합니다. 원본을 들어 주세요.', SOME, PAST)
    assert '기록이 없어' not in text and PAST in text and text.endswith('원본을 들어 주세요.')
    facts = [{'id': 'comparison.model_windows', 'text': PAST}]
    assert past_comparison_fact(facts, '지난번과 비교해서 어떤 케어가 필요할까요?') == PAST
    assert past_comparison_fact(facts, '짖은 횟수는 몇번?') is None  # only for comparison questions
    assert past_comparison_fact([{'id': 'current.samples', 'text': 'x'}], '지난번과 비교해 줘') is None


def test_other_statements_of_missing_records_are_left_alone():
    # No earlier outing known to the server (no past fact), or a statement about something else: nothing is rewritten.
    assert '과거 기록이 없어' in with_audio_lead('비교할 과거 기록이 없어 근거가 부족합니다.', SOME, None)
    kept = with_audio_lead('아직 확인 의견 기록이 없습니다. 원본을 들어 주세요.', SOME, PAST)
    assert '확인 의견 기록이 없습니다' in kept and PAST not in kept
