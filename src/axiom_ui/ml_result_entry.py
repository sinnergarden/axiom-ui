"""Explicit empty entry; saved registrations use render_saved_workbench instead."""


def render_empty_stock_ml_entry() -> str:
    """Render a static absence notice without opening Research or Engine inputs."""
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Axiom · 机器学习结果状态</title>
<style>
body{margin:0;background:#f3f6fa;color:#25374d;font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
main{max-width:760px;margin:48px auto;padding:0 22px}
section{background:white;border:1px solid #dce5ef;border-radius:12px;padding:26px;margin:20px 0}
h1{font-size:27px;margin:10px 0}h2{font-size:19px;margin:0 0 10px}
.small{font-size:13px;color:#52677e}a{color:#416e99}nav{display:flex;gap:20px;flex-wrap:wrap}
</style>
</head>
<body>
<main>
<p class="small">AXIOM · 研究工作台 · 公开只读</p>
<h1>机器学习结果</h1>
<section id="empty-stock-ml-result" role="status">
<h2>尚无可展示的保存结果</h2>
<p>当前公开入口尚未绑定 Research 保存登记，因此没有可核验的模型、信号或账户结果。教程只说明流程与用例，不代表回测已完成。</p>
<p class="small">保存登记和结果经公共 Reader 核对后，才会在此提供对应的只读页面。</p>
</section>
<nav><a href="ml-engineering.html">阅读机器学习教程</a><a href="index.html">返回实验结果入口</a></nav>
</main>
</body>
</html>"""
