"""Check the new shell and unchanged approved history; never read owner roots."""
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import re
import sys


# Exact bytes retained from reviewed base f29d21bef7d12541b1f1d47dfab2f23d6c7b3aad.
LEGACY_SHA256 = {'etf-three-account.html': '911de1a6652fe6a39a53b86e564ff9d670a465df325ebe47bb0d4f0416cbfc16', 'echarts.LICENSE.txt': '634293835b43a6dd2094fa39182a3d9a6b9ca43b7fdb9ac354e8037af2a3093a', 'echarts.NOTICE.txt': 'd491d358344f842685c1b1585970999db65fe30ecf7ef3867af8814f4016c016', 'echarts.vendor.json': '2f11f91cce4d25104c76415ddb5a8fecc83ed99aa4f58b1c3805f988eb641b0c', 'publication.json': 'c8ccf61df86c4d8720017050ac810290be2ed49b294b63865fa1429d016ae23a'}

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in {"href", "src"} and value)


def check(root):
    root = Path(root)
    shell = {'index.html', 'app.css', 'app.js', 'config.js', '.nojekyll'}
    expected = shell | set(LEGACY_SHA256)
    paths = list(root.rglob('*'))
    assert all(not path.is_symlink() for path in paths), 'symlink in public bundle'
    assert {p.name for p in paths if p.is_file()} == expected, 'unexpected public file'
    assert all(p.parent == root for p in paths), 'nested public content refused'
    for name, digest in LEGACY_SHA256.items():
        assert sha256((root / name).read_bytes()).hexdigest() == digest, ("historical file changed", name)
    for name in shell:
        path = root / name
        text = path.read_text()
        assert not re.search(r'/Users/|/home/|\.artifacts/|sha256:[0-9a-f]{64}|github_pat_|ghp_', text), path.name
        assert 'workbench-data' not in text, 'embedded result payload'
    links = Links()
    links.feed((root / 'index.html').read_text())
    assert 'etf-three-account.html' in links.links, 'missing historical report entry'
    for link in links.links:
        assert link in expected and (root / link).is_file(), ('invalid shell link', link)
    config = (root / 'config.js').read_text()
    assert re.search(r"window.AXIOM_RESULTS_ENDPOINT = '(?:https://[a-zA-Z0-9.-]+(?::[0-9]+)?)?';", config), 'invalid public endpoint'
    print('Pages PASS: five clean shell files, valid home links, five byte-identical approved historical files.')


if __name__ == '__main__':
    check(sys.argv[1])
