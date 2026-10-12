from scripts.prepare_audioset_bark_strong import source_candidates
from scripts.train_audioset_bark_lstm import window_label
from scripts.evaluate_audioset_strong_bark import evaluate
from scripts.train_yamnet_patch_lstm import patch_labels


def test_strong_label_selection_and_window_boundaries():
    lines = [
        'videoA_0\t4.95\t5.20\t/m/05tny_\n',
        'videoA_0\t0.0\t1.0\t/m/09x0r\n',
        'videoB_0\t1.0\t2.0\t/m/03wwcy\n',
        'videoC_0\t1.0\t2.0\t/m/09x0r\n',
    ]
    positive, negative = source_candidates(lines)
    assert {row['clip_id'] for row in positive} == {'videoA_0'}
    assert {row['clip_id'] for row in negative} == {'videoB_0', 'videoC_0'}
    assert window_label(positive[0]['bark_intervals_s'], 0) == 0
    assert window_label(positive[0]['bark_intervals_s'], 1) == 1


def test_strong_eval_keeps_window_and_clip_metrics_separate():
    records = [{'clip_id': 'one', 'window': 0, 'label': 1,
                'bark_overlap_s': .3, 'labels': ['/m/05tny_']},
               {'clip_id': 'one', 'window': 1, 'label': 0,
                'bark_overlap_s': 0, 'labels': ['/m/05tny_']},
               {'clip_id': 'two', 'window': 0, 'label': 0,
                'bark_overlap_s': 0, 'labels': []}]
    result = evaluate(records, [.8, .2, .7], .5)
    assert result['window']['confusion'] == {'tp': 1, 'fp': 1, 'fn': 0, 'tn': 1}
    assert result['clip']['confusion'] == {'tp': 1, 'fp': 1, 'fn': 0, 'tn': 0}


def test_patch_labels_keep_short_bark_and_exclude_distant_patches():
    labels = patch_labels([(1.1, 1.35)], 20)
    assert labels.sum() >= 1
    assert labels[0] == 0
    assert labels[-1] == 0
