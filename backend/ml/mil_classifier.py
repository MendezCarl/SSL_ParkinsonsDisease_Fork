from __future__ import annotations

import torch
import torch.nn as nn


class WindowEncoder(nn.Module):
    """Encodes each window into a fixed-size embedding via stacked LSTM."""

    def __init__(self, input_size: int = 24, embed_dim: int = 64) -> None:
        super().__init__()
        self.lstm1 = nn.LSTM(input_size, 32, batch_first=True)
        self.lstm2 = nn.LSTM(32, 64, batch_first=True)
        self.lstm3 = nn.LSTM(64, embed_dim, batch_first=True)
        self.drop = nn.Dropout(0.4)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (n_windows, T, 24)
        x, _ = self.lstm1(x)
        x = self.drop(x)
        x, _ = self.lstm2(x)
        x = self.drop(x)
        _, (h, _) = self.lstm3(x)
        return h.squeeze(0)  # (n_windows, embed_dim)


class AttentionPool(nn.Module):
    """Learns a scalar attention weight per window and returns weighted sum."""

    def __init__(self, embed_dim: int = 64, hidden_dim: int = 32) -> None:
        super().__init__()
        self.attn = nn.Sequential(
            nn.Linear(embed_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, H: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # H: (n_windows, embed_dim)
        scores = self.attn(H)  # (n_windows, 1)
        weights = torch.softmax(scores, dim=0)  # (n_windows, 1)
        z = (weights * H).sum(dim=0)  # (embed_dim,)
        return z, weights.squeeze(1)


class MILClassifier(nn.Module):
    def __init__(self, input_size: int = 24, embed_dim: int = 64, n_classes: int = 4) -> None:
        super().__init__()
        self.encoder = WindowEncoder(input_size, embed_dim)
        self.pool = AttentionPool(embed_dim)
        self.drop = nn.Dropout(0.4)
        self.fc1 = nn.Linear(embed_dim, 32)
        self.fc2 = nn.Linear(32, n_classes)
        self.relu = nn.ReLU()

    def forward(self, bag: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # bag: (1, n_windows, T, 24)
        H = self.encoder(bag.squeeze(0))
        z, weights = self.pool(H)
        z = self.drop(self.relu(self.fc1(z)))
        return self.fc2(z).unsqueeze(0), weights
