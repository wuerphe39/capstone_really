from petmind.backend.schemas import PetContext
from petmind.backend.services.frequency import compare_candidate_frequency


def context():
    return PetContext(observed_behavior='unknown', behavior_duration_seconds=0,
                      bark_detected=True, bark_count=2, window_s=5)


def test_different_window_lengths_compare_rates_not_counts():
    # Current 2 events / 5s is higher than historical 8 events / 30s.
    result = compare_candidate_frequency(context(), {'status': 'ok',
        'stats': {'bark_candidates_per_minute': 16, 'sample_count': 1}})
    assert result['current_candidates_per_minute'] == 24
    assert result['delta_per_minute'] == 8
    assert result['basis'].endswith('not_validated_normal_baseline')


def test_zero_history_is_distinct_from_missing_or_failed_retrieval():
    empty = compare_candidate_frequency(context(), {'status': 'ok', 'stats': {}})
    failed = compare_candidate_frequency(context(), {'status': 'failed', 'stats': {}})
    zero = compare_candidate_frequency(context(), {'status': 'ok',
        'stats': {'bark_candidates_per_minute': 0, 'sample_count': 1}})
    assert empty['status'] == 'insufficient_data' and empty['delta_per_minute'] is None
    assert failed['status'] == 'retrieval_failed'
    assert zero['status'] == 'ok' and zero['delta_per_minute'] == 24
