"""Build a local, read-only UI preview from a reviewed Docs HTML export.

The source stays in axiom-docs. This copies the current site into an ignored
preview directory; it never edits publication.json or the tracked site.
"""

import argparse
import base64
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree


DOCS = "https://github.com/sinnergarden/axiom-docs/blob/"
SOURCE_NOTEBOOK = "notebooks/ml_engineering_tutorial.ipynb"
SOURCE_HTML = "notebooks/ml_engineering_tutorial.html"
PAGE = "ml-engineering.html"
SENSITIVE = re.compile(
    r"(?:file://)?/(?:Users|tmp|private|var/folders|home)/|"
    r"[A-Za-z]:\\|\.artifacts/|sediment://|"
    r"github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
)
SVG_IMAGE = re.compile(r'src="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"')
HREF = re.compile(r'href="([^"]+)"')
SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.I | re.S)
CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
       "base-uri 'none'; form-action 'none'")


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


def check_svg(data):
    decoded = data.decode("utf-8")
    root = ElementTree.fromstring(decoded)
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("tutorial image is not SVG")
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() in {"script", "foreignobject"}:
            raise ValueError("active SVG element")
        for key, value in element.attrib.items():
            name = key.rsplit("}", 1)[-1].lower()
            if name.startswith("on") or (name.endswith("href") and not value.startswith("#")):
                raise ValueError("active or external SVG link")
    if any(not value.strip(' "\'').startswith("#")
           for value in re.findall(r"url\(([^)]+)\)", decoded, re.I)):
        raise ValueError("external SVG style resource")
    if SENSITIVE.search(decoded):
        raise ValueError("sensitive SVG content")
    return digest(data)


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.sources = []
        self.links = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if "src" in values:
            self.sources.append(values["src"])
        if "href" in values:
            self.links.append(values["href"])
        if tag == "script":
            self.scripts += 1
        if tag in {"iframe", "object", "embed", "form", "link"} or any(
            key.startswith("on") for key in values
        ):
            raise ValueError("active tutorial element or handler")


def transform(raw, expected_sha, docs_commit):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha):
        raise ValueError("expected SHA must be sha256:<64 lowercase hex>")
    if not re.fullmatch(r"[0-9a-f]{40}", docs_commit):
        raise ValueError("Docs commit must be a full fixed SHA")
    if digest(raw) != expected_sha:
        raise ValueError("Docs HTML differs from reviewed digest")
    html = raw.decode("utf-8")
    if not html.startswith("<!doctype html>") or '<section id="section-14"' not in html:
        raise ValueError("unexpected tutorial document")
    if SENSITIVE.search(html):
        raise ValueError("private path or credential-like source content")
    inventory = Inventory()
    inventory.feed(html)
    if inventory.scripts != 1 or len(inventory.sources) != 1:
        raise ValueError("unexpected script or resource count")
    if len(SVG_IMAGE.findall(html)) != 1:
        raise ValueError("expected one embedded architecture diagram")
    svg_sha = check_svg(base64.b64decode(SVG_IMAGE.search(html).group(1), validate=True))
    html, removed = SCRIPT.subn("", html)
    if removed != 1:
        raise ValueError("expected one removable navigation script")

    def rewrite(match):
        target = match.group(1)
        if target.startswith("#"):
            if target[1:] not in inventory.ids:
                raise ValueError("missing tutorial anchor: " + target)
            return match.group(0)
        if target.startswith("https://"):
            return match.group(0)
        if target == "researcher_tutorial.html":
            path = "notebooks/researcher_tutorial.ipynb"
        elif target.startswith(("../docs/", "../examples/")):
            path = target[3:]
            if ".." in path.split("/"):
                raise ValueError("unsafe Docs link")
        else:
            raise ValueError("unresolved tutorial link: " + target)
        return 'href="' + DOCS + docs_commit + "/" + path + '"'

    html = HREF.sub(rewrite, html)
    if html.count("</head>") != 1 or html.count("<header>") != 1:
        raise ValueError("unexpected tutorial layout")
    html = html.replace("</head>", '<style>header a{color:#d3eaff;text-decoration:underline}'
                        'header a:hover{color:#fff}</style>'
                        '<meta http-equiv="Content-Security-Policy" content="'
                        + CSP + '"></head>', 1)
    html = html.replace(
        "<header>", '<header><p><a href="index.html">← 返回结果入口</a> · '
        '<a href="' + DOCS + docs_commit + "/" + SOURCE_NOTEBOOK
        + '">Docs 源 Notebook</a></p>', 1,
    )
    final = Inventory()
    final.feed(html)
    if final.scripts or final.sources != inventory.sources or SENSITIVE.search(html):
        raise ValueError("unsafe transformed page")
    if any(not (link.startswith("https://") or link == "index.html" or link.startswith("#"))
           for link in final.links):
        raise ValueError("unresolved transformed link")
    return html.encode("utf-8"), svg_sha


def prepare(source_html, expected_sha, docs_commit, site, preview):
    site = Path(site).resolve(strict=True)
    preview = Path(preview).resolve()
    if site == preview or site in preview.parents or preview in site.parents:
        raise ValueError("preview must be separate from the source site")
    if preview.exists() or site.is_symlink():
        raise ValueError("preview must be new and source site must be a directory")
    if not (site / "index.html").is_file() or not (site / "publication.json").is_file():
        raise ValueError("expected existing static UI site")
    page, svg_sha = transform(Path(source_html).read_bytes(), expected_sha, docs_commit)
    original_index = (site / "index.html").read_bytes()
    index = original_index.decode("utf-8")
    marker = '<section><details><summary>结果口径与来源</summary>'
    if index.count(marker) != 1 or 'id="ml-engineering-tutorial"' in index:
        raise ValueError("expected one current result entry insertion point")
    card = ('<section class="result-card" id="ml-engineering-tutorial">'
            '<h2>ML 工程教程 · 语义验收预览</h2>'
            '<p>历史两折证据与当前 Feature 进展；新代码单元尚未执行。'
            'Label 贯通及完整四折账户验收待完成。</p>'
            '<a href="ml-engineering.html">阅读教程</a></section>')
    index = index.replace(marker, card + marker, 1)
    shutil.copytree(site, preview / "site", symlinks=False)
    (preview / "site" / PAGE).write_bytes(page)
    (preview / "site" / "index.html").write_text(index, encoding="utf-8")
    etf_name = "etf-three-account.html"
    etf_before = (site / etf_name).read_bytes()
    etf_after = (preview / "site" / etf_name).read_bytes()
    if etf_before != etf_after:
        raise ValueError("ETF page changed in local preview")
    report = {
        "status": "local_preview_only",
        "published": False,
        "source_repo": "sinnergarden/axiom-docs",
        "source_commit": docs_commit,
        "source_html_path": SOURCE_HTML,
        "source_html_sha256": expected_sha,
        "embedded_svg_sha256": svg_sha,
        "preview_html_sha256": digest(page),
        "source_index_sha256": digest(original_index),
        "preview_index_sha256": digest(index.encode("utf-8")),
        "etf_source_sha256": digest(etf_before),
        "etf_preview_sha256": digest(etf_after),
        "publication_unchanged": (site / "publication.json").read_bytes()
        == (preview / "site" / "publication.json").read_bytes(),
    }
    (preview / "acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-html", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--docs-commit", required=True)
    parser.add_argument("--site", required=True)
    parser.add_argument("--preview", required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_html, args.expected_sha, args.docs_commit,
                             args.site, args.preview), ensure_ascii=False, indent=2))
