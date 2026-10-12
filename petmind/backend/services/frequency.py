"""Comparable candidate rates from measured windows; not a long-term pet baseline."""
def compare_candidate_frequency(context, evidence):
    current = context.bark_count * 60 / context.window_s
    previous = evidence.get('stats', {}).get('bark_candidates_per_minute')
    status = 'retrieval_failed' if evidence['status'] != 'ok' else 'insufficient_data' if previous is None else 'ok'
    return {'status': status, 'current_window_s': context.window_s,
            'current_candidates_per_minute': current,
            'historical_candidates_per_minute': previous if status == 'ok' else None,
            'delta_per_minute': current-previous if status == 'ok' else None,
            'historical_window_count': evidence.get('stats', {}).get('sample_count', 0),
            'basis': 'stored_observation_windows_not_validated_normal_baseline'}
