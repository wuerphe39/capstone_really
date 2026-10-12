import numpy as np

from pet_monitor.tracking import Candidate, TrackSelector


def dog(identity, x=.2, color=0):
    appearance = np.zeros(4); appearance[color] = 1
    return Candidate(identity, np.array([x,.2,x+.2,.6]), .8, appearance)


def establish(selector, identity=1):
    for t in [0., .2, .4]:
        selected, event = selector.select([dog(identity)], t)
    assert selected.track_id == identity
    return event


def test_short_id_change_can_keep_sequence_with_unique_spatial_appearance_match():
    selector = TrackSelector(); establish(selector)
    selected, event = selector.select([dog(2,.21)], .6)
    assert selected.track_id == 2
    assert event['event'] == 'short_gap_association' and not event['reset_sequence']


def test_short_gap_reconnect_does_not_require_box_overlap():
    selector = TrackSelector(); establish(selector)
    # Center moves 14.5% of frame; boxes no longer overlap, but appearance and
    # scale still support a cautious one-frame association.
    selected, event = selector.select([dog(2,.345)], .6)
    assert selected.track_id == 2
    assert event['event'] == 'short_gap_association' and not event['reset_sequence']


def test_long_gap_reacquires_but_never_stitches_old_motion():
    selector = TrackSelector(); original = establish(selector)
    assert selector.select([dog(2)], 5.)[0] is None
    assert selector.select([dog(2)], 5.2)[0] is None
    selected, event = selector.select([dog(2)], 5.4)
    assert selected.track_id == 2 and event['reset_sequence']
    assert event['segment_id'] > original['segment_id']


def test_crossing_dogs_or_different_appearance_cannot_be_short_gap_associated():
    selector = TrackSelector(); establish(selector)
    selected, event = selector.select([dog(1), dog(2,.21)], .6)
    assert selected is None and selector.ambiguous
    assert selector.select([dog(2)], .8)[0] is None
    selector = TrackSelector(); establish(selector)
    assert selector.select([dog(2,color=1)], .6)[0] is None


def test_reused_id_after_long_gap_still_resets_and_multiple_dogs_do_not_reacquire():
    selector = TrackSelector(); establish(selector)
    assert selector.select([dog(1),dog(2,.7)], 5.)[0] is None
    for t in [5.2,5.4,5.6]:
        selected,event=selector.select([dog(1)],t)
    assert selected.track_id == 1 and event['reset_sequence']
