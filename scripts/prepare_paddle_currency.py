"""Supplement real receipt crops with explicitly synthetic currency/amount lines."""
import hashlib
import json
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont
import pymupdf


def main():
    root = Path('data/paddle-finetune/currency')
    if root.exists():
        raise SystemExit('Currency export already exists; preserve it or select a new dataset version.')
    fonts = {
        'train': [Path('C:/Windows/Fonts') / f for f in ['arial.ttf', 'arialbd.ttf', 'times.ttf', 'timesbd.ttf', 'calibri.ttf', 'calibrib.ttf', 'segoeui.ttf']],
        'validation': [Path('C:/Windows/Fonts') / f for f in ['cour.ttf', 'verdana.ttf', 'tahoma.ttf', 'consola.ttf']],
    }
    symbols = ['₹', '$', '€', '£', '¥']
    for font in sum(fonts.values(), []):
        face = pymupdf.Font(fontfile=str(font))
        assert all(face.has_glyph(ord(c), fallback=False) for c in symbols), str(font)
    audit = {'synthetic_only': True, 'split': 'disjoint font families and random seeds', 'splits': {}}
    for split, count, seed in [('train', 4000, 871), ('validation', 600, 872)]:
        out = root / split; out.mkdir(parents=True)
        rng = random.Random(seed)
        records = []
        for i in range(count):
            symbol = symbols[i % len(symbols)]
            amount = f'{rng.randint(0, 99999):,}.{rng.randint(0, 99):02d}'
            if rng.random() < .25: amount = amount.replace(',', '')
            gap = rng.choice(['', ' ', ' '])
            text = rng.choice(['', 'TOTAL ', 'Tax ', 'Price ', 'Amount ']) + symbol + gap + amount
            path = rng.choice(fonts[split]); font = ImageFont.truetype(str(path), rng.randint(12, 40))
            x0,y0,x1,y1 = font.getbbox(text)
            image = Image.new('RGB', (x1-x0+10, y1-y0+10), (255,255,255))
            ImageDraw.Draw(image).text((5-x0,5-y0), text, font=font, fill=(rng.randint(0,70),)*3)
            image = image.rotate(rng.uniform(-2,2), resample=Image.Resampling.BICUBIC, expand=True, fillcolor='white')
            if rng.random() < .4: image = image.filter(ImageFilter.GaussianBlur(rng.uniform(.1,.5)))
            dest = out / f'{i:05d}.png'; image.save(dest)
            records.append({'image': dest.resolve().as_posix(), 'text': text, 'source': 'synthetic_currency',
                            'font': path.name, 'symbol': symbol})
        (root / f'{split}.txt').write_text(''.join(f"{r['image']}\t{r['text']}\n" for r in records), encoding='utf-8')
        (root / f'{split}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records), encoding='utf-8')
        audit['splits'][split] = {'samples': count, 'seed': seed, 'fonts': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in fonts[split]},
                                'labels_sha256': hashlib.sha256((root/f'{split}.txt').read_bytes()).hexdigest()}
    (root/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps(audit))


if __name__ == '__main__': main()
