import torch
import torch.nn as nn
from torchvision import models

LABELS = ["happy", "sad", "angry", "neutral"]
NUM_CLASSES = len(LABELS)


class EmotionClassifier(nn.Module):
    def __init__(self, num_classes: int = NUM_CLASSES, pretrained: bool = True):
        super().__init__()
        self.backbone = models.efficientnet_b0(
            weights=models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        )
        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=0.3),
            nn.Linear(in_features, num_classes),
        )

    def forward(self, x):
        return self.backbone(x)
