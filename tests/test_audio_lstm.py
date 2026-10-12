import numpy as np
import soundfile as sf
import torch

from pet_monitor.audio_lstm import AudioClassifier, AudioPredictor, binary_metrics, logmel
from scripts.prepare_esc50 import separate_sources


def test_features_resample_stereo_and_models(tmp_path):
    path = tmp_path/'tone.wav'
    t = np.arange(22050)/22050
    sf.write(path, np.column_stack([np.sin(t*440*2*np.pi)*.1]*2),22050)
    features = logmel(path)
    assert features.shape == (251,40) and torch.isfinite(features).all()
    for kind in ('lstm','pooled'):
        assert AudioClassifier(kind)(features[None]).shape == (1,2)


def test_metrics_report_imbalance_and_false_alarms():
    result = binary_metrics([1,1,0,0],[.9,.1,.8,.1])
    assert result['confusion'] == {'tp':1,'fp':1,'fn':1,'tn':1}
    assert result['precision'] == result['recall'] == result['f1'] == .5


def test_official_source_overlap_is_removed_without_touching_test():
    records = [{'src_file':'a','sha256':'1','split':'validation'},
               {'src_file':'a','sha256':'2','split':'test'},
               {'src_file':'b','sha256':'2','split':'train'},
               {'src_file':'c','sha256':'3','split':'train'}]
    kept, excluded = separate_sources(records)
    assert kept == [records[1], records[3]]
    assert len(excluded) == 2


def test_audio_inference_covers_all_windows_and_marks_padding(tmp_path):
    checkpoint = tmp_path/'test.pt'
    model = AudioClassifier('pooled')
    torch.save({'state_dict':model.state_dict(),'mean':torch.zeros(40),'std':torch.ones(40),
                'kind':'pooled','threshold':.5,'labels':['other','dog'],'sample_rate':16000,'window_s':5},checkpoint)
    path = tmp_path/'six.wav'
    sf.write(path,np.zeros(16000*6),16000)
    result = AudioPredictor(checkpoint).predict(path)
    assert [(w['start_s'],w['end_s'],w['padded']) for w in result['windows']] == [(0,5,False),(5,6,True)]
