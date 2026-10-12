import pytest
from pet_monitor.event_video import EventPlanner, candidate_windows


def test_roll_overlap_merge_wait_and_long_event_bound():
    planner=EventPlanner()
    planner.add(10,15,'a')
    assert planner.drain(20)==[]  # wait for a later pre-roll overlap
    planner.add(20,25,'b')
    assert planner.drain(34)==[]
    event=planner.drain(35)[0]
    assert (event.start,event.end,event.clip_ids)==(5,30,['a','b'])
    for t in range(0,160,5): planner.add(t,t+5,str(t))
    assert all(e.end-e.start<=60 for e in planner.drain(0,final=True))


def test_no_trigger_without_valid_lstm_and_invalid_bounds():
    assert candidate_windows({'context':{'bark':{'count':5}}})==[]
    assert candidate_windows({'audio_lstm':{'threshold':float('nan'),'windows':[]}})==[]
    assert candidate_windows({'audio_lstm':{'threshold':.9,'windows':[
        {'start_s':0,'end_s':5,'dog_score':.89}]}})==[]
    with pytest.raises(ValueError): EventPlanner(pre_s=-1)
    with pytest.raises(ValueError): EventPlanner().add(5,0,'a')


def test_segment_boundary_seek_never_uses_scientific_notation(tmp_path,monkeypatch):
    from scripts import monitor_audio_events as monitor
    from pet_monitor.event_video import EventWindow
    calls=[]
    monkeypatch.setattr(monitor,'run_ffmpeg',lambda exe,args:calls.append(args))
    segments=[{'path':tmp_path/'seg-000000.mp4','start':5.064063,'end':10.064063}]
    monitor.export_event('ffmpeg',segments,EventWindow(5.064063+1e-15,10,['a']),tmp_path)
    assert calls[0][calls[0].index('-ss')+1]=='0.000000'
