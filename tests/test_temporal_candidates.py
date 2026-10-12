from pet_monitor.temporal_candidates import short_activity, stabilize, diagnostics


def points(speed=0):
    return [{'t': i/5, 'cx': .2+speed*i/5, 'cy': .5, 'segment_id': 1} for i in range(16)]


def test_short_activity_keeps_camera_identity_and_missing_data_unknown():
    assert short_activity(points(.05), 3)['label'] == 'unknown'
    assert short_activity(points(.05), 3, True)['label'] == 'locomotion'
    assert short_activity(points(), 3, True)['label'] == 'non_locomotion'
    assert short_activity(points(.05)[:-3], 3, True)['label'] == 'unknown'
    mixed = points(.05); mixed[-1]['segment_id'] = 2
    assert short_activity(mixed, 3, True)['label'] == 'unknown'


def test_stabilization_is_causal_and_never_fills_unknown():
    sequence = [{'t': i/5, 'label': label} for i, label in enumerate(
        ['moving', 'moving', 'still', 'unknown', 'still', 'moving'])]
    result = stabilize(sequence)
    assert [p['label'] for p in result] == ['moving', 'moving', 'moving', 'unknown', 'still', 'moving']
    assert stabilize(sequence[:3]) == result[:3]
    assert sequence[2]['label'] == 'still'


def test_diagnostics_uses_duration_not_frame_count():
    report = {'duration_s': 3, 'predictions': [
        {'t': 0, 'label': 'unknown', 'reason': 'warmup'}, {'t': 2, 'label': 'moving'}]}
    result = diagnostics(report)
    assert result['unknown_reason_seconds'] == {'warmup': 2}
    assert result['decision_ratio'] == 1/3
