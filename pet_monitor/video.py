"""Public video -> one dog track -> synthetic-trained LSTM; camera motion uncompensated."""
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from .detection import unique_dog_indices
from .lstm import LSTMPredictor
from .motion import Observation
from .tracking import Candidate, TrackSelector


def appearance_histogram(frame, box):
    x1, y1, x2, y2 = map(int, box)
    height, width = frame.shape[:2]
    crop = frame[max(0,y1):min(height,y2), max(0,x1):min(width,x2)]
    if not crop.size:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [12, 8], [0, 180, 0, 256]).ravel()
    return hist/max(1, hist.sum())


def dog_class_id(names):
    items = names.items() if isinstance(names, dict) else enumerate(names)
    matches = [int(index) for index, name in items if name == 'dog']
    if len(matches) != 1:
        raise ValueError('detector needs exactly one dog class')
    return matches[0]


def analyze_video(path, checkpoint='artifacts/lstm/trajectory_lstm.pt', output='artifacts/video',
                  detector_checkpoint='artifacts/models/yolov8n.pt', detector_conf=.1,
                  detector_imgsz=640):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    Path('artifacts/models').mkdir(parents=True, exist_ok=True)
    detector = YOLO(str(detector_checkpoint))
    dog_class = dog_class_id(detector.names)
    predictor = LSTMPredictor(checkpoint)
    capture = cv2.VideoCapture(str(path))
    native_fps = capture.get(cv2.CAP_PROP_FPS)
    if not capture.isOpened() or not np.isfinite(native_fps) or native_fps <= 0:
        capture.release()
        raise ValueError('video cannot be decoded or has invalid FPS')
    stride = max(1, round(native_fps / 5))
    # ByteTrack needs intermediate motion updates; feeding it only the 5 Hz
    # inference frames fragments IDs on 60 fps source footage.
    tracking_stride = max(1, round(native_fps / 15))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(output / 'tracked.mp4'), cv2.VideoWriter_fourcc(*'mp4v'), native_fps/stride, (width, height))
    if not writer.isOpened():
        capture.release()
        raise ValueError('output video encoder unavailable')
    selector, frame_index = TrackSelector(), 0
    points, sequence, predictions, tracking_diagnostics = [], [], [], []
    try:
        while frame_index / native_fps < 120:
            ok, frame = capture.read()
            if not ok:
                break
            t = frame_index / native_fps
            frame_index += 1
            sample_frame = (frame_index - 1) % stride == 0
            if not sample_frame and (frame_index - 1) % tracking_stride:
                continue
            result = detector.track(frame, persist=True, classes=[dog_class], tracker='bytetrack.yaml',
                                    verbose=False, conf=detector_conf, imgsz=detector_imgsz)[0]
            matched = None
            visible_ids = []
            candidates = []
            dog_detections = len(result.boxes)
            if result.boxes.id is not None and len(result.boxes):
                ids = result.boxes.id.int().cpu().tolist()
                xyxy = result.boxes.xyxy.cpu().numpy()
                confidences = result.boxes.conf.cpu().tolist()
                retained = unique_dog_indices(xyxy, confidences)
                dog_detections = len(retained)
                visible_ids = [ids[i] for i in retained]
                for i in retained:
                    track_id, box, confidence = ids[i], xyxy[i], confidences[i]
                    candidates.append(Candidate(track_id, box/np.array([width,height,width,height]), confidence,
                                                appearance_histogram(frame, box)))
            selected, association = selector.select(candidates, t, dog_detections)
            if association['reset_sequence']:
                # Short missing detections may interpolate; ambiguity/crossings never do.
                if association['event'] == 'new_segment_reacquisition' or selector.ambiguous or (sequence and t-sequence[-1].t > .65):
                    sequence = []
            if selected is not None:
                matched = selected.box*np.array([width,height,width,height])
            if matched is not None:
                x1, y1, x2, y2 = matched
                observation = Observation(t, float((x1+x2)/2/width), float((y1+y2)/2/height))
                sequence.append(observation)
                points.append(asdict(observation) | {'track_id': selector.target_id, 'segment_id': selector.segment})
            elif sequence and t-sequence[-1].t > .65:
                sequence = []
            if not sample_frame:
                continue
            prediction = predictor.predict(sequence) if matched is not None else {
                'label': 'unknown', 'confidence': None, 'reason': 'selected dog track missing'}
            predictions.append({'t': t, **prediction})
            tracking_diagnostics.append({'t': t, 'dog_detections': dog_detections,
                                         'raw_dog_detections': len(result.boxes),
                                         'visible_track_ids': visible_ids, 'selected_track_id': selector.target_id,
                                         'selected_track_matched': matched is not None, **association})
            annotated = result.plot()
            cv2.putText(annotated, 'LSTM: ' + prediction['label'], (15, 35), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
            writer.write(annotated)
            if len(predictions) == 1:
                cv2.imwrite(str(output / 'preview.jpg'), annotated)
    finally:
        capture.release(); writer.release()
    duration = frame_index / native_fps
    durations = defaultdict(float)
    for i, prediction in enumerate(predictions):
        end = predictions[i+1]['t'] if i+1 < len(predictions) else duration
        durations[prediction['label']] += max(0, end-prediction['t'])
    return {'filename': Path(path).name, 'duration_s': duration, 'source_fps': native_fps,
            'sample_fps': native_fps/stride, 'target_track_id': selector.target_id, 'tracked_samples': len(points),
            'points': points, 'predictions': predictions, 'seconds_by_label': dict(durations),
            'tracking_diagnostics': tracking_diagnostics,
            'dominant': max(durations, key=durations.get) if durations else 'unknown',
            'motion_model': 'lstm_synthetic', 'real_behavior_accuracy': None,
            'training_source': predictor.training_source, 'feature_version': predictor.feature_version,
            'camera_motion_compensated': False, 'max_interpolation_gap_s': .65,
            'detector_checkpoint': str(detector_checkpoint), 'detector_conf': detector_conf,
            'detector_imgsz': detector_imgsz,
            'tracking_fps': native_fps/tracking_stride,
            'tracking_policy': 'conservative_association_new_segment_on_reacquisition',
            'annotated_video': str(output / 'tracked.mp4')}
