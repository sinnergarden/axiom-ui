"""Check the shell-only Pages tree; never read private owner roots."""
from pathlib import Path
import re
import sys


def check(root):
    root = Path(root)
    expected = {'index.html', 'app.css', 'app.js', 'config.js', '.nojekyll'}
    paths = list(root.rglob('*'))
    assert all(not path.is_symlink() for path in paths), 'symlink in public bundle'
    assert {p.name for p in paths if p.is_file()} == expected, 'unexpected public file'
    assert all(p.parent == root for p in paths), 'nested public content refused'
    for path in paths:
        text = path.read_text()
        assert not re.search(r'/Users/|/home/|\.artifacts/|sha256:[0-9a-f]{64}|github_pat_|ghp_', text), path.name
        assert 'workbench-data' not in text, 'embedded result payload'
    config = (root / 'config.js').read_text()
    assert re.search(r"window.AXIOM_RESULTS_ENDPOINT = '(?:https://[a-zA-Z0-9.-]+(?::[0-9]+)?)?';", config), 'invalid public endpoint'
    print('Remote shell PASS: five static files; no result payload or private local path.')


if __name__ == '__main__':
    check(sys.argv[1])
