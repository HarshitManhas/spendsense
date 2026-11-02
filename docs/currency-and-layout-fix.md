# Currency symbols and separated receipt details

Updated 2 November 2026.

## Cause and implemented fix

The uploaded two-page invoice was being rasterized and passed through English OCR even though it already contained selectable text. Its thin serif rupee sign was misread as letters, digits or a pound sign. The old parser also merged horizontally separate seller/buyer columns and treated whole table rows as item names.

The application now tries bounded native PDF extraction first. It preserves Unicode currency characters, word coordinates and table cells. Scanned/image-only PDFs fall back to OCR, as do pages that provide only a text footer without usable totals/items. [PyMuPDF documents the word and table extraction APIs used here](https://pymupdf.readthedocs.io/en/latest/page.html).

The new layout parser:

- Separates seller and billing columns and prefers an explicit seller label.
- Prefers the invoice/receipt date over order/payment timestamps; ambiguous dates still require review.
- Maps table headings to description, quantity, unit price, net amount, tax amount and gross amount. Wrapped descriptions remain one product; shipping can remain a separate item. When a net column is present, item line totals use it, while the receipt total includes tax.
- Preserves repeated-space column gaps before whitespace normalization. Ordinary spaces within a multiword merchant/product remain part of that name. Handles a whole OCR line such as `Green Tea 2 ₹50.00 ₹100.00` as name, quantity, unit price and line total.
- Recognizes supported explicit currency codes and signs including ₹/INR, €/EUR, £/GBP, RM/MYR, Rp/IDR, US$/USD and JPY with ¥. A bare `$`, `¥` or `Rs` is ambiguous across countries and stays unresolved without compatible code evidence. Conflicting evidence requires review.
- Parses Indian grouping (`₹1,23,456.78`) and space-separated thousands inside a money cell. Positional column boundaries are applied before interpreting monetary strings.

The old five-field benchmark file `ocr_fields.py` was not changed: SHA-256 remains `dd2ef158aecb5bee03e7f845c00380fb6d734eef7762e999ae348c3cf0251751`. Its 78.6% benchmark is not a score for the new layout parser.

## Actual invoice verification

The latest upload's two unedited, unapproved drafts were re-extracted with revision guards. Earlier uploads, human corrections and approved expenses were not overwritten. Both now show INR and invoice date `2026-06-06`.

- Product invoice: seller separated from the buyer, total 22,449.00, tax 3,424.42, product unit/net price 19,024.58 and separate shipping row (unit 33.90, net 0.00 after discount).
- Fee invoice: seller separated from the buyer, total 5.00, tax 0.76, Marketplace Fees unit/net price 4.24. Quantity remains blank because it was not printed.

Drafts now offer **Re-extract**, with a warning that new predictions replace draft values. This action never approves the expense. Refresh/reopen an already open review to see refreshed values.

## Currency-symbol training performed

A small CNN was trained locally on 6,000 synthetic isolated glyphs, with 1,200 validation examples from separate font families. Classes are ₹, $, €, £, ¥ and a noncurrency class. It does not train receipt fields or expense categories. Each run records font hashes, validation confusion counts and checkpoint selection; generated fonts/images/checkpoints remain local and ignored by Git.

Training uses installed fonts and public [Playfair Display](https://github.com/google/fonts/tree/main/ofl/playfairdisplay); [Noto Serif](https://github.com/google/fonts/tree/main/ofl/notoserif) is an additional validation family. Downloads include their OFL files and a pinned Google Fonts commit in `data/currency-fonts/sources.json`. Libre Baskerville was checked but excluded because it lacks one or more required glyphs. No receipt image was used as a training example.

| Run | Synthetic validation | Known invoice diagnostic |
|---|---|---|
| v2: initial Windows fonts | 99.33%, epoch 8 | 0/18 rupee glyphs; 294/300 noncurrency glyphs correct |
| v3: added serif style | 98.25%, epoch 6 | 14/18 rupee glyphs; 292/300 noncurrency glyphs correct |
| v4: variable weight and smaller glyphs | 95.50%, epoch 14 | 14/18 rupee glyphs; 296/300 noncurrency glyphs correct |

The synthetic validation task changed when extra fonts/sizes were introduced, so these are not identical benchmarks. The invoice diagnostic was used to guide font coverage: it is development feedback, not an untouched test score. It uses PDF-supplied character locations and does not validate symbol detection on scanned receipts.

**No glyph checkpoint is enabled in automatic extraction.** The remaining misses and false currency classifications make that premature. The deployed PDF/text/layout fixes work independently. For scanned images whose symbols OCR misreads, manual currency confirmation remains necessary until a diverse, labeled real-image symbol/detection evaluation passes. Next training data should include thin/bold serif marks, small scans, compression, rotation and confusing digits/letters; evaluate complete sign detection plus classification, not just isolated glyphs.

Reproduce the latest training run using a fresh output directory:

```powershell
uv run --extra ml python -m ai_expense_scanner.ml.currency_symbols --output artifacts/currency-symbols-next --epochs 15 --extra-train-font "data/currency-fonts/playfairdisplay/PlayfairDisplay[wght].ttf" --extra-validation-font "data/currency-fonts/notoserif/NotoSerif[wdth,wght].ttf"
```

Evidence: `artifacts/currency-symbols-v4/report.json`, `model.pt`, and `invoice-diagnostic.json`. No CORD/SROIE currency labels were invented, and their test split was not used.

## Validation

56 Python tests pass, including currency ambiguity, grouping, column gaps, multiword names, seller/buyer separation, date priority, wrapped table descriptions, PDF page selection, scanned/footers fallback and existing MongoDB isolation/approval tests. Three frontend tests and the TypeScript/Vite production build pass. The existing large-bundle advisory remains. Live worker processing of the two real invoice drafts completed successfully with `source=pdf_text`; they remain awaiting human approval.
