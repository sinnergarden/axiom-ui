"""Attach one reviewed axiom-docs HTML tutorial to the selected static site.

The notebook and its generated HTML remain owned by axiom-docs. This tool
only rewrites site-relative links, validates the embedded public diagram, and records
the immutable source identity. It never executes notebook cells.
"""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import re
from xml.etree import ElementTree


DOCS = 'https://github.com/sinnergarden/axiom-docs/blob/'
SOURCE_PATH = 'notebooks/ml_engineering_tutorial.html'
HTML_NAME = 'ml-engineering.html'
SECTION = ('<section id="ml-engineering-tutorial"><h2>ML 工程 Notebook</h2>'
           '<p>从统一设计的固定公开教程生成，展示工程架构、Feature registry、'
           '有界实测汇总与代码示例。</p><a href="ml-engineering.html">'
           '阅读工程 Notebook</a></section>')
SENSITIVE = re.compile(r'(?:file://)?/(?:Users|tmp|private|var/folders|home)/|'
                       r'[A-Za-z]:\\|\.artifacts/|sediment://|'
                       r'github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}|'
                       r'AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')
IMAGE = re.compile(r'src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"')
LINK = re.compile(r'href="([^"]+)"')


def digest(data):
    return 'sha256:' + sha256(data).hexdigest()


def safe_svg(data):
    decoded = data.decode('utf-8')
    root = ElementTree.fromstring(decoded)
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError('tutorial image is not SVG')
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1].lower() in {'script', 'foreignobject'}:
            raise ValueError('active SVG content is forbidden')
        for key, value in element.attrib.items():
            name = key.rsplit('}', 1)[-1].lower()
            if name.startswith('on') or (name.endswith('href') and not value.startswith('#')):
                raise ValueError('active or external SVG link is forbidden')
    if any(not value.strip(' "\'').startswith('#')
           for value in re.findall(r'url\(([^)]+)\)', decoded, flags=re.I)):
        raise ValueError('external SVG style resource is forbidden')
    if SENSITIVE.search(decoded):
        raise ValueError('sensitive SVG content is forbidden')


def attach(source_html, source_commit, expected_source_sha256, site):
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('source commit must be a full fixed SHA')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', expected_source_sha256):
        raise ValueError('expected source digest must be sha256:<64 hex>')
    site = Path(site)
    if site.is_symlink() or not (site / 'publication.json').is_file():
        raise ValueError('a checked static site directory is required')
    original = Path(source_html).read_bytes()
    if digest(original) != expected_source_sha256:
        raise ValueError('Docs HTML differs from the reviewed source digest')
    html = original.decode('utf-8')
    if not html.startswith('<!doctype html>') or '<section id="section-13"' not in html:
        raise ValueError('unexpected ML tutorial document')
    if SENSITIVE.search(html):
        raise ValueError('sensitive path or credential-like HTML content')
    if len(IMAGE.findall(html)) != 1:
        raise ValueError('expected one public architecture diagram')
    svg = base64.b64decode(IMAGE.search(html).group(1), validate=True)
    safe_svg(svg)
    if re.search(r'<(?:iframe|object|embed|form|link)\b|\bon[a-z]+\s*=', html, flags=re.I):
        raise ValueError('active tutorial HTML element or handler is forbidden')
    if len(re.findall(r'\bsrc="([^"]+)"', html)) != 1:
        raise ValueError('unexpected tutorial resource')
    # The owner-rendered script only adds notebook navigation convenience. The
    # public copy remains a static, script-free teaching page.
    html, script_count = re.subn(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S | re.I)
    if script_count != 1:
        raise ValueError('unexpected tutorial script count')

    def link(match):
        target = match.group(1)
        if target.startswith('#') or target.startswith('https://'):
            return match.group(0)
        if target == 'researcher_tutorial.html':
            return 'href="' + DOCS + source_commit + '/notebooks/researcher_tutorial.ipynb"'
        if (target.startswith(('../docs/', '../examples/'))
                and not any(part == '..' for part in target[3:].split('/'))):
            return 'href="' + DOCS + source_commit + '/' + target[3:] + '"'
        raise ValueError('unresolved tutorial link: ' + target)

    html = LINK.sub(link, html)
    style_end = '</style></head>'
    if html.count(style_end) != 1:
        raise ValueError('unexpected tutorial stylesheet')
    html = html.replace(style_end, '@media(max-width:980px){section.markdown{overflow-x:auto}}'
                        + style_end, 1)
    html = html.replace('<header>', '<header><a style="color:#c5e8ff" href="index.html">'
                        '← 公开结果入口</a> · <a style="color:#c5e8ff" href="'
                        + DOCS + source_commit + '/notebooks/ml_engineering_tutorial.ipynb">'
                        '统一 Docs 源 Notebook</a><br>', 1)
    if html.count('href="index.html"') != 1 or SENSITIVE.search(html):
        raise ValueError('invalid public tutorial navigation or content')
    page = html.encode('utf-8')

    index = (site / 'index.html').read_text()
    marker = '<section><h2>展示范围</h2>'
    if index.count(marker) != 1 or 'id="ml-engineering-tutorial"' in index:
        raise ValueError('site index cannot accept exactly one tutorial link')
    index = index.replace(marker, SECTION + marker, 1)
    manifest = json.loads((site / 'publication.json').read_text())
    if manifest.get('tutorial') or manifest.get('authorization') != 'explicit_selected_public_results':
        raise ValueError('unexpected site publication state')
    manifest['tutorial'] = {
        'file': HTML_NAME,
        'diagram_embedded': True,
        'source_repo': 'sinnergarden/axiom-docs',
        'source_commit': source_commit,
        'source_path': SOURCE_PATH,
        'source_html_sha256': expected_source_sha256,
        'published_html_sha256': digest(page),
        'diagram_sha256': digest(svg),
        'status': 'public_readonly_teaching',
        'business_execution': False,
    }
    (site / HTML_NAME).write_bytes(page)
    (site / 'index.html').write_text(index)
    (site / 'publication.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest['tutorial']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-html', required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--site', required=True)
    args = parser.parse_args()
    print(json.dumps(attach(args.source_html, args.source_commit,
                            args.expected_source_sha256, args.site), ensure_ascii=False))
