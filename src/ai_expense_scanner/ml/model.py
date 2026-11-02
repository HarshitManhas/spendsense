from dataclasses import dataclass

import torch
from torch import nn


@dataclass
class ModelConfig:
    height: int = 224
    width: int = 224
    dimension: int = 256
    heads: int = 4
    layers: int = 3
    feedforward: int = 1024
    dropout: float = .1
    max_length: int = 512


class ExpenseModel(nn.Module):
    def __init__(self, vocab_size: int, config: ModelConfig):
        super().__init__()
        self.config = config
        channels = [3, 32, 64, 96, 128]
        blocks = []
        for before, after in zip(channels, channels[1:]):
            blocks.extend([nn.Conv2d(before, after, 3, stride=2, padding=1), nn.GroupNorm(8, after), nn.GELU()])
        self.encoder = nn.Sequential(*blocks)
        self.project = nn.Linear(128, config.dimension)
        self.row_position = nn.Embedding((config.height + 15) // 16, config.dimension)
        self.col_position = nn.Embedding((config.width + 15) // 16, config.dimension)
        self.embedding = nn.Embedding(vocab_size, config.dimension, padding_idx=0)
        self.position = nn.Embedding(config.max_length, config.dimension)
        layer = nn.TransformerDecoderLayer(config.dimension, config.heads, config.feedforward,
                                          config.dropout, batch_first=True)
        self.decoder = nn.TransformerDecoder(layer, config.layers)
        # Decoder clones start identical in PyTorch; initialize each matrix independently.
        for parameter in self.decoder.parameters():
            if parameter.ndim > 1:
                nn.init.xavier_uniform_(parameter)
        self.output = nn.Linear(config.dimension, vocab_size)

    def encode(self, images):
        features = self.encoder(images)
        height, width = features.shape[-2:]
        rows = self.row_position(torch.arange(height, device=images.device))
        cols = self.col_position(torch.arange(width, device=images.device))
        return self.project(features.flatten(2).transpose(1, 2)) + (rows[:, None] + cols[None, :]).flatten(0, 1)

    def decode(self, memory, tokens):
        length = tokens.shape[1]
        target = self.embedding(tokens) + self.position(torch.arange(length, device=tokens.device))
        mask = torch.triu(torch.ones(length, length, device=tokens.device, dtype=torch.bool), diagonal=1)
        decoded = self.decoder(target, memory, tgt_mask=mask, tgt_key_padding_mask=tokens.eq(0))
        return self.output(decoded)

    def forward(self, images, tokens):
        return self.decode(self.encode(images), tokens)

    @torch.inference_mode()
    def generate(self, images, max_length=None):
        self.eval()
        memory = self.encode(images)
        tokens = torch.ones(images.shape[0], 1, dtype=torch.long, device=images.device)
        finished = torch.zeros(images.shape[0], dtype=torch.bool, device=images.device)
        for _ in range(min(max_length or self.config.max_length, self.config.max_length) - 1):
            logits = self.decode(memory, tokens)[:, -1]
            logits[:, :2] = float('-inf')  # Never generate PAD or BOS as content.
            next_token = logits.argmax(-1).masked_fill(finished, 2)
            tokens = torch.cat([tokens, next_token[:, None]], dim=1)
            finished |= next_token.eq(2)
            if finished.all():
                break
        return tokens
