"""Experimental classifier over frozen, time-ordered YAMNet embeddings."""
import torch
from torch import nn


EMBEDDING_SIZE = 1024


class YamnetEmbeddingClassifier(nn.Module):
    def __init__(self, kind='lstm'):
        super().__init__()
        if kind not in {'lstm', 'pooled'}:
            raise ValueError('kind must be lstm or pooled')
        self.kind = kind
        self.project = nn.Sequential(nn.Linear(EMBEDDING_SIZE, 64), nn.LayerNorm(64), nn.Tanh())
        self.temporal = nn.LSTM(64, 32, batch_first=True) if kind == 'lstm' else None
        self.head = nn.Linear(32 if kind == 'lstm' else 64, 1)

    def forward(self, embeddings, lengths):
        if embeddings.ndim != 3 or embeddings.shape[-1] != EMBEDDING_SIZE:
            raise ValueError('expected [windows, patches, 1024] YAMNet embeddings')
        if lengths.ndim != 1 or len(lengths) != len(embeddings) or (lengths < 1).any():
            raise ValueError('one positive patch count is required per window')
        if (lengths > embeddings.shape[1]).any():
            raise ValueError('patch count exceeds padded input')
        projected = self.project(embeddings)
        if self.temporal is not None:
            packed = nn.utils.rnn.pack_padded_sequence(
                projected, lengths.cpu(), batch_first=True, enforce_sorted=False)
            _, (hidden, _) = self.temporal(packed)
            values = hidden[-1]
        else:
            mask = torch.arange(embeddings.shape[1], device=lengths.device)[None, :] < lengths[:, None]
            values = (projected * mask.unsqueeze(-1)).sum(1) / lengths.unsqueeze(-1)
        return self.head(values).squeeze(-1)
