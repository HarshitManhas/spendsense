"""Small glyph classifier: synthetic currency symbols, not receipt field/category training."""
import argparse
import hashlib
import json
from pathlib import Path
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import torch
from torch import nn

LABELS = ['₹', '$', '€', '£', '¥', 'none']
VERSION = 'currency-glyph-cnn-v1'


def normalize(image):
    image = image.convert('L')
    array = np.asarray(image)
    ys, xs = np.where(array < 180)
    canvas = Image.new('L', (32, 32), 255)
    if len(xs):
        glyph = image.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        glyph.thumbnail((24, 26), Image.Resampling.LANCZOS)
        canvas.paste(glyph, ((32 - glyph.width) // 2, (32 - glyph.height) // 2))
    return torch.from_numpy((1 - np.asarray(canvas, dtype=np.float32) / 255).copy()).unsqueeze(0)


class GlyphModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Flatten(), nn.Linear(64 * 4 * 4, 64), nn.ReLU(), nn.Linear(64, len(LABELS)))

    def forward(self, value):
        return self.layers(value)


def samples(fonts, count, seed):
    rng = random.Random(seed)
    images, targets = [], []
    for i in range(count):
        label = i % len(LABELS)
        glyph = LABELS[label] if label < 5 else rng.choice('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz%#*|+-.,/')
        path = rng.choice(fonts)
        font = ImageFont.truetype(str(path), rng.randint(9, 52))
        try:
            axes = font.get_variation_axes()
            font.set_variation_by_axes([rng.randint(int(axis['minimum']), int(axis['maximum']))
                                       if axis['name'] == b'Weight' else axis['default'] for axis in axes])
        except OSError:
            pass  # Static Windows fonts have no variable axes.
        image = Image.new('L', (96, 96), 255)
        ImageDraw.Draw(image).text((48, 48), glyph, font=font, fill=rng.randint(0, 85), anchor='mm')
        image = image.rotate(rng.uniform(-7, 7), fillcolor=255, resample=Image.Resampling.BICUBIC)
        if rng.random() < .6:
            image = image.filter(ImageFilter.GaussianBlur(rng.uniform(.1, .7)))
        images.append(normalize(image)); targets.append(label)
    return torch.stack(images), torch.tensor(targets)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fonts', type=Path, default=Path('C:/Windows/Fonts'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--epochs', type=int, default=15)
    p.add_argument('--extra-train-font', type=Path, action='append', default=[])
    p.add_argument('--extra-validation-font', type=Path, action='append', default=[])
    args = p.parse_args()
    if args.output.exists(): p.error('Use a new output directory')
    if args.epochs < 1: p.error('--epochs must be positive')
    train_fonts = [args.fonts / name for name in ['arial.ttf', 'arialbd.ttf', 'times.ttf', 'timesbd.ttf',
                                                  'calibri.ttf', 'calibrib.ttf', 'segoeui.ttf', 'segoeuib.ttf']]
    validation_fonts = [args.fonts / name for name in ['cour.ttf', 'verdana.ttf', 'tahoma.ttf', 'consola.ttf']]
    train_fonts += args.extra_train_font
    validation_fonts += args.extra_validation_font
    if {f.resolve() for f in train_fonts} & {f.resolve() for f in validation_fonts}:
        p.error('Training and validation font files must not overlap; keep entire families separate')
    import pymupdf
    for path in train_fonts + validation_fonts:
        font = pymupdf.Font(fontfile=str(path))
        if not all(font.has_glyph(ord(symbol), fallback=False) for symbol in LABELS[:5]):
            p.error(f'Font does not contain every currency sign: {path}')
    torch.manual_seed(73); torch.set_num_threads(4)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    train_x, train_y = samples(train_fonts, 6000, 73)
    val_x, val_y = samples(validation_fonts, 1200, 74)
    train_x, train_y, val_x, val_y = [t.to(device) for t in (train_x, train_y, val_x, val_y)]
    model = GlyphModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001)
    args.output.mkdir(parents=True)
    history = []
    best_accuracy = -1
    best_epoch = 0
    for epoch in range(args.epochs):
        model.train(); order = torch.randperm(len(train_y), device=device); loss_sum = 0
        for indices in order.split(128):
            optimizer.zero_grad(set_to_none=True)
            loss = nn.functional.cross_entropy(model(train_x[indices]), train_y[indices])
            loss.backward(); optimizer.step(); loss_sum += loss.item() * len(indices)
        model.eval()
        with torch.inference_mode():
            logits = torch.cat([model(batch) for batch in val_x.split(128)])
            predicted = logits.argmax(1)
            accuracy = (predicted == val_y).float().mean().item()
        record = {'epoch': epoch + 1, 'train_loss': loss_sum / len(train_y), 'validation_accuracy': accuracy}
        history.append(record); print(json.dumps(record), flush=True)
        (args.output / 'status.json').write_text(json.dumps(record))
        if accuracy > best_accuracy:
            best_accuracy, best_epoch = accuracy, epoch + 1
            torch.save({'version': VERSION, 'labels': LABELS,
                        'state_dict': {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                        'synthetic_training_only': True}, args.output / 'model.pt')
    model.load_state_dict(torch.load(args.output / 'model.pt', map_location=device, weights_only=True)['state_dict'])
    with torch.inference_mode():
        predicted = torch.cat([model(batch) for batch in val_x.split(128)]).argmax(1)
    confusion = torch.zeros(len(LABELS), len(LABELS), dtype=torch.int64)
    for truth, guess in zip(val_y.cpu(), predicted.cpu()): confusion[truth, guess] += 1
    report = {'version': VERSION, 'labels': LABELS, 'training_samples': 6000, 'validation_samples': 1200,
              'training_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'augmentation': {'font_size': [9, 52], 'variable_weights': True, 'rotation_degrees': [-7, 7],
                               'blur_radius': [.1, .7], 'ink': [0, 85]},
              'split': 'unseen font families; independent random seed', 'device': device,
              'font_hashes': {str(f.name): hashlib.sha256(f.read_bytes()).hexdigest() for f in train_fonts + validation_fonts},
              'training_fonts': [f.name for f in train_fonts], 'validation_fonts': [f.name for f in validation_fonts],
              'history': history, 'confusion': confusion.tolist(), 'validation_accuracy': best_accuracy,
              'selected_epoch': best_epoch, 'selection': 'maximum held-out-font validation accuracy',
              'limitations': ['Synthetic isolated glyphs only; not receipt OCR accuracy.',
                             'Dollar and yen signs identify glyphs, not unique currencies.',
                             'No private receipt images used for training. Not installed automatically.']}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
