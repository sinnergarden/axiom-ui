"""Prepare one reviewed Docs tutorial excerpt as an unpublished UI preview.

Only the current progress, workflow and CaseC/A/B material are copied. Historical
sections 1–13, old result tables, the source navigation and notebook links stay out.
"""

import argparse
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil


DOCS = "https://github.com/sinnergarden/axiom-docs/blob/"
SOURCE_HTML = "notebooks/ml_engineering_tutorial.html"
PAGE = "ml-engineering.html"
SENSITIVE = re.compile(
    r"(?:file://)?/(?:Users|tmp|private|var/folders|home)/|"
    r"[A-Za-z]:\\|\.artifacts/|sediment://|"
    r"github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
)
OLD_RESULT_MARKERS = (
    "两个真实移动窗口", "同 Signal 换组合", "Feb5", "Feb19",
    "2024-01-02", "37.72 s", "282.34 s", "Top3/Top5",
    "历史回执读取代码", "M2 检验 CAGR",
)
CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
CARD = ('<section class="result-card" id="ml-engineering-tutorial">'
        '<h2>机器学习研究</h2><p>查看流程、用例与当前进展。</p>'
        '<a href="ml-engineering.html">阅读教程</a></section>')


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


class Inventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []
        self.scripts = 0
        self.resources = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if "href" in values:
            self.links.append(values["href"])
        if "src" in values:
            self.resources.append(values["src"])
        if tag == "script":
            self.scripts += 1
        if tag in {"iframe", "object", "embed", "form", "link"} or any(
            key.startswith("on") for key in values
        ):
            raise ValueError("active excerpt element or handler")


def transform(raw, expected_sha, docs_commit):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha):
        raise ValueError("expected SHA must be sha256:<64 lowercase hex>")
    if not re.fullmatch(r"[0-9a-f]{40}", docs_commit):
        raise ValueError("Docs commit must be a full fixed SHA")
    if digest(raw) != expected_sha:
        raise ValueError("Docs HTML differs from reviewed digest")
    source = raw.decode("utf-8")
    if not source.startswith("<!doctype html>"):
        raise ValueError("unexpected tutorial document")
    styles = re.findall(r"<style>(.*?)</style>", source, re.S)
    if len(styles) != 1:
        raise ValueError("expected one owner stylesheet")
    start = '<section id="section-14" class="markdown">'
    end = "</main>"
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("expected reviewed CaseC/A/B boundary")
    excerpt = source.split(start, 1)[1].split(end, 1)[0]
    excerpt = start + excerpt
    if excerpt.count('<section id="cell-35"') != 1:
        raise ValueError("expected result-recording section")
    # The final paragraph of cell-35 is a longer-term roadmap, outside this
    # public flow and current-progress excerpt.
    excerpt, removed = re.subn(r"<p>小例之后沿同一实现做 M1 多年.*?</p>", "", excerpt,
                               count=1, flags=re.S)
    if removed != 1:
        raise ValueError("expected one later-roadmap paragraph")
    excerpt = excerpt.replace('id="section-14"', 'id="cases"', 1)
    excerpt = excerpt.replace("<h2>14. 三个小用例：从正式输入到保存结果</h2>",
                              "<h2>三个用例：从正式输入到保存结果</h2>", 1)
    excerpt = excerpt.replace("第 1–13 节的历史回执无须加载。", "本公开节选不含历史回执。")
    for original, replacement in (
        ('id="cell-20"', 'id="inputs"'),
        ('id="cell-22"', 'id="case-c"'),
        ('id="cell-33"', 'id="case-a"'),
        ('id="cell-34"', 'id="case-b"'),
        ('id="cell-35"', 'id="checks"'),
        ("14.1 CaseC：", "CaseC："),
        ("14.2 CaseA：", "CaseA："),
        ("14.3 CaseB：", "CaseB："),
        ("14.4 结果记录", "结果记录"),
    ):
        if excerpt.count(original) != 1:
            raise ValueError("unexpected reviewed excerpt marker: " + original)
        excerpt = excerpt.replace(original, replacement, 1)
    # These are the only two links in the selected Case material. They refer
    # to design concepts, not saved results or the full source notebook.
    for path in (
        "docs/design/04_axiom_trade.md#stock-bounded-v7-proposal",
        "docs/design/04_axiom_trade.md#long-history-evaluation",
    ):
        old = 'href="../' + path + '"'
        if excerpt.count(old) != 1:
            raise ValueError("unexpected Case design link: " + path)
        excerpt = excerpt.replace(old, 'href="' + DOCS + docs_commit + "/" + path + '"', 1)
    progress = (
        '<section id="progress" class="markdown"><h1>机器学习研究：当前进展</h1>'
        '<p>505 交易日 Feature 的完整验收已通过。真实 20 日旧、新实现对照记录提速 '
        '29.43%；这个数字仅适用于该次对照。</p>'
        '<p>Label 统一修正代码已完成两轮独立审查，整段贯通验证尚未通过。'
        '完整四折训练和账户尚未运行；CaseA 两字段候选只有 helper unit 结果，'
        '真实保存闭环待验；CaseB 通用保存组合待实现。</p>'
        '<p>下方代码单元均未执行、没有新结果。实际输入由各 owner 交接后再逐项验收。</p>'
        '</section>'
        '<section id="workflow" class="markdown"><h2>流程与职责</h2>'
        '<p>Feature/Label → Model → 原始 Prediction → 组合 Signal → 信号评价 → '
        '策略账户。Data 保存事实；Research 管训练输入、模型、预测与信号评价；'
        'Engine 管账户执行和评价；UI 只读展示保存结果。</p>'
        '<p>训练只读取拟合截止时已成熟的 Label；预测的可用时间、独立评价 Label '
        '与执行日须分别核对。这里展示接口和待验条件，不代表回测或收益验收。</p>'
        '</section>'
    )
    nav = ('<nav><a href="#progress">当前进展</a><a href="#workflow">流程与职责</a>'
           '<a href="#cases">三个用例</a><a href="#inputs">通用输入配置</a>'
           '<a href="#case-c">CaseC：四折与 Top5</a>'
           '<a href="#case-a">CaseA：训练配置</a>'
           '<a href="#case-b">CaseB：组合评价</a>'
           '<a href="#checks">验收顺序</a></nav>')
    page = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Axiom · 机器学习研究：流程与当前进展</title><style>'
            + styles[0] + '\nheader a{color:#d3eaff;text-decoration:underline}'
            'header a:hover{color:#fff}</style>'
            '<meta http-equiv="Content-Security-Policy" content="' + CSP + '"></head>'
            '<body><header><b>Axiom · 机器学习研究</b>'
            '<p>流程、三个用例与当前进展 · 未执行的示例明确标注</p>'
            '<a href="index.html">← 返回研究工作台</a></header>'
            '<div class="layout">' + nav + '<main>' + progress + excerpt
            + '</main></div></body></html>')
    inventory = Inventory()
    inventory.feed(page)
    if inventory.scripts or inventory.resources:
        raise ValueError("public excerpt must have no scripts or embedded resources")
    if any(marker in page for marker in OLD_RESULT_MARKERS):
        raise ValueError("historical result material remained in public excerpt")
    if SENSITIVE.search(page) or re.search(r"sha256:[0-9a-f]{64}", page):
        raise ValueError("private path, credential or saved artifact identity in excerpt")
    if any(link.startswith("#") and link[1:] not in inventory.ids
           or not (link.startswith("#") or link == "index.html"
                   or link.startswith(DOCS + docs_commit + "/docs/design/"))
           for link in inventory.links):
        raise ValueError("unresolved or out-of-scope public link")
    return page.encode("utf-8")


def prepare(source_html, expected_sha, docs_commit, site, preview):
    site_path = Path(site)
    site = site_path.resolve(strict=True)
    preview = Path(preview).resolve()
    if site == preview or site in preview.parents or preview in site.parents:
        raise ValueError("preview must be separate from the source site")
    if preview.exists() or site_path.is_symlink():
        raise ValueError("preview must be new and source site must be a directory")
    if not (site / "index.html").is_file() or not (site / "publication.json").is_file():
        raise ValueError("expected existing static UI site")
    page = transform(Path(source_html).read_bytes(), expected_sha, docs_commit)
    original_index = (site / "index.html").read_bytes()
    index = original_index.decode("utf-8")
    marker = '<section><details><summary>结果口径与来源</summary>'
    if index.count(marker) != 1 or 'id="ml-engineering-tutorial"' in index:
        raise ValueError("expected one current entry insertion point")
    index = index.replace(marker, CARD + marker, 1)
    shutil.copytree(site, preview / "site", symlinks=False)
    (preview / "site" / PAGE).write_bytes(page)
    (preview / "site" / "index.html").write_text(index, encoding="utf-8")
    etf_name = "etf-three-account.html"
    etf_before = (site / etf_name).read_bytes()
    etf_after = (preview / "site" / etf_name).read_bytes()
    if etf_before != etf_after:
        raise ValueError("ETF page changed in local preview")
    report = {
        "status": "local_preview_only", "published": False,
        "source_repo": "sinnergarden/axiom-docs", "source_commit": docs_commit,
        "source_html_path": SOURCE_HTML, "source_html_sha256": expected_sha,
        "excerpt": "current_progress_workflow_and_case_c_a_b_only",
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
