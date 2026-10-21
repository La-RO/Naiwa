"""Build browser-readable data without fetch, so file:// works too."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
images = json.loads((ROOT / 'data/images.json').read_text(encoding='utf-8'))
videos = json.loads((ROOT / 'data/videos.json').read_text(encoding='utf-8'))
output = (
    '// Generated from the two JSON catalogues. Run update_catalogue.py after editing.\n'
    + 'window.NAIWA_IMAGES = ' + json.dumps(images, ensure_ascii=False, indent=2) + ';\n'
    + 'window.NAIWA_VIDEOS = ' + json.dumps(videos, ensure_ascii=False, indent=2) + ';\n'
)
(ROOT / 'data/catalogue.js').write_text(output, encoding='utf-8')
print(f'Catalogue ready: {len(images)} images, {len(videos)} videos.')
