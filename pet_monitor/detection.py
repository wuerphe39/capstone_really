"""Conservative duplicate suppression for dog-only detections.

Keep spatially separate dogs distinct so multi-dog footage stays ambiguous.
"""
import numpy as np


def unique_dog_indices(boxes, confidences):
    boxes = np.asarray(boxes, dtype=float)
    confidences = np.asarray(confidences, dtype=float)
    if boxes.shape != (len(confidences), 4) or not np.isfinite(boxes).all() or not np.isfinite(confidences).all():
        raise ValueError('invalid dog detections')
    kept = []
    for index in np.argsort(-confidences):
        box = boxes[index]
        area = max(0, box[2]-box[0])*max(0, box[3]-box[1])
        duplicate = False
        for other in kept:
            reference = boxes[other]
            other_area = max(0, reference[2]-reference[0])*max(0, reference[3]-reference[1])
            lower = np.maximum(box[:2], reference[:2])
            upper = np.minimum(box[2:], reference[2:])
            intersection = np.prod(np.maximum(0, upper-lower))
            union = area+other_area-intersection
            if min(area, other_area) > 0 and intersection/min(area, other_area) >= .8 and union > 0 and intersection/union >= .2:
                duplicate = True
                break
        if not duplicate:
            kept.append(int(index))
    return kept
