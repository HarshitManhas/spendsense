"""Generate an explicitly fictional receipt for local workflow testing."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

target = Path('data/demo/sample-receipt.png')
target.parent.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (600, 850), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=22)
heading = ImageFont.load_default(size=32)
draw.text((70, 65), 'SAMPLE RECEIPT', fill='#233e32', font=heading)
draw.text((70, 115), 'Fictional data - for testing only', fill='#777777', font=font)
draw.line((70, 175, 530, 175), fill='#bbbbbb', width=2)
for y, text in [(220, 'Merchant: Sample Cafe'), (275, 'Date: 2026-11-01'), (350, 'Coffee and lunch      INR 349.00'),
                (440, 'TOTAL                 INR 349.00'), (500, 'Currency: INR'), (565, 'Tax: not specified'),
                (690, 'Thank you for trying SpendSense.')]:
    draw.text((70, y), text, fill='#333333', font=font)
image.save(target)
print(target.resolve())
