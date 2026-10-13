"""Pin the exact trusted workbench script/style hashes in the public shell CSP."""
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'src/axiom_ui/assets'


def trusted_hashes():
    script = '\n;\n'.join((ASSETS / name).read_text() for name in
                           ('echarts.6.1.0.min.js', 'workbench-interactions.js', 'workbench.js'))
    return [b64encode(sha256(value.encode()).digest()).decode() for value in
            (script, (ASSETS / 'workbench.css').read_text())]


if __name__ == '__main__':
    script, style = trusted_hashes()
    path = ROOT / 'site/index.html'
    text = re.sub(r"script-src [^;]+;", "script-src 'self' 'sha256-" + script + "';", path.read_text())
    text = re.sub(r"style-src [^;]+;", "style-src 'self' 'sha256-" + style + "';", text)
    path.write_text(text)
