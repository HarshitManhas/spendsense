"""Extract native PDF words/cell geometry in a bounded subprocess."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def read_pdf_page(content, page_number):
    if not content.startswith(b'%PDF-'):
        return None
    with tempfile.TemporaryDirectory(prefix='spendsense-text-') as directory:
        root = Path(directory)
        (root / 'input.pdf').write_bytes(content)
        try:
            result = subprocess.run([sys.executable, '-m', 'ai_expense_scanner.pdf_text', str(root), str(page_number)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode:
                return None
            page = json.loads((root / 'page.json').read_text(encoding='utf-8'))
            return page if len(page['lines']) >= 8 else None
        except subprocess.TimeoutExpired:
            return None


def extract(root, page_number):
    import pymupdf
    with pymupdf.open(root / 'input.pdf') as document:
        if document.is_encrypted or not 1 <= page_number <= min(len(document), 5):
            raise ValueError('Invalid PDF page')
        page = document[page_number - 1]
        words = page.get_text('words')
        if len(words) > 20000:
            raise ValueError('PDF text exceeds supported range')
        result = {'width': page.rect.width, 'height': page.rect.height,
                  'lines': [{'text': w[4], 'box': list(w[:4]), 'confidence': 1.0} for w in words], 'tables': []}
        for table in page.find_tables().tables:
            data = table.extract()
            if not data:
                continue
            headers = [{'text': text or '', 'box': list(box)} for text, box in zip(data[0], table.rows[0].cells) if box]
            result['tables'].append({'headers': headers, 'box': list(table.bbox)})
        (root / 'page.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    extract(Path(sys.argv[1]), int(sys.argv[2]))
