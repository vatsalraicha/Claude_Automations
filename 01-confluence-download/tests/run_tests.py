#!/usr/bin/env python3
"""Self-test for convert.py and verify.py. Builds a small fake download in a temp folder.

Run:  python 01-confluence-download/tests/run_tests.py
Exit code 0 and the last line "ALL TESTS PASSED" mean both scripts work on this machine.
"""
import csv
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOOP = HERE.parent
PY = sys.executable

COLUMNS = ["page_id", "title", "space_key", "parent_id", "type", "version", "last_modified", "source_url",
           "attachment_count", "empty_body", "status", "attempts", "raw_path", "md_path", "placeholders",
           "verified_at", "notes"]

RICH = """<ac:layout><ac:layout-section ac:type="single"><ac:layout-cell>
<h1>Billing overview</h1>
<p>The <strong>billing service</strong> charges customers on the <em>first business day</em> of each month.<br/>Late payments accrue 1.5% interest per month; see order_line_items and snake_case_name.</p>
<h2>Rules &amp; limits</h2>
<ul>
  <li>Invoices above 10,000 EUR need approval from <ac:link><ri:user ri:account-id="abc123"/></ac:link>
    <ul><li>Approval expires after 14 days</li><li>Second <code>level_two</code> item</li></ul>
  </li>
  <li>Refunds are processed within 5 days, see <ac:link><ri:page ri:content-title="Refund process"/><ac:plain-text-link-body><![CDATA[the refund page]]></ac:plain-text-link-body></ac:link></li>
  <li>External policy: <ac:link><ri:page ri:content-title="Legal policy" ri:space-key="LEGAL"/></ac:link></li>
</ul>
<ol><li>Collect usage</li><li>Generate invoice</li><li>Send email</li></ol>
<ac:task-list>
<ac:task><ac:task-id>7</ac:task-id><ac:task-status>complete</ac:task-status><ac:task-body>Migrate tax tables</ac:task-body></ac:task>
<ac:task><ac:task-id>8</ac:task-id><ac:task-status>incomplete</ac:task-status><ac:task-body>Review dunning letters</ac:task-body></ac:task>
</ac:task-list>
<h2>Fee table</h2>
<table><tbody>
<tr><th>Plan</th><th>Monthly fee</th><th>Notes</th></tr>
<tr><td>Basic</td><td>9 EUR</td><td>Up to 3 users | no SSO</td></tr>
<tr><td>Pro</td><td>49 EUR</td><td><p>Unlimited users</p><p>Includes SSO</p></td></tr>
</tbody></table>
<h3>Regional matrix</h3>
<table><tbody>
<tr><th colspan="2">Region and currency</th><th>Tax</th></tr>
<tr><td rowspan="2">Europe</td><td>EUR</td><td>VAT 21 percent</td></tr>
<tr><td>GBP</td><td><ac:structured-macro ac:name="code"><ac:parameter ac:name="language">sql</ac:parameter><ac:plain-text-body><![CDATA[SELECT rate FROM vat WHERE country = 'GB';]]></ac:plain-text-body></ac:structured-macro></td></tr>
</tbody></table>
<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:parameter ac:name="title">Cut-off time</ac:parameter><ac:rich-text-body><p>Orders after 17:00 CET are billed the next day.</p></ac:rich-text-body></ac:structured-macro>
<ac:structured-macro ac:name="code"><ac:parameter ac:name="language">python</ac:parameter><ac:parameter ac:name="linenumbers">true</ac:parameter><ac:plain-text-body><![CDATA[def late_fee(amount):
    # 1.5% per month
    return amount * 0.015 if amount > 0 else 0  # <b>not html</b>
]]></ac:plain-text-body></ac:structured-macro>
<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">Historic exceptions</ac:parameter><ac:rich-text-body><p>Until 2021 the fee was 2 percent.</p></ac:rich-text-body></ac:structured-macro>
<p>Current state: <ac:structured-macro ac:name="status"><ac:parameter ac:name="colour">Green</ac:parameter><ac:parameter ac:name="title">LIVE</ac:parameter></ac:structured-macro> tracked in <ac:structured-macro ac:name="jira"><ac:parameter ac:name="server">Jira</ac:parameter><ac:parameter ac:name="key">BILL-142</ac:parameter></ac:structured-macro>.</p>
<p><ac:structured-macro ac:name="toc"><ac:parameter ac:name="maxLevel">3</ac:parameter></ac:structured-macro></p>
<p><ac:structured-macro ac:name="jira"><ac:parameter ac:name="jqlQuery">project = BILL AND status = Open</ac:parameter></ac:structured-macro></p>
<p><ac:image ac:alt="Billing flow"><ri:attachment ri:filename="billing flow.png"/></ac:image></p>
<p>Spec: <ac:link><ri:attachment ri:filename="spec.pdf"/></ac:link> and <a href="https://example.com/docs?a=1&amp;b=2">vendor docs</a>. Reviewed on <time datetime="2024-03-05"/> <ac:emoticon ac:name="tick"/>.</p>
<p>Formula: a * b &lt; c, tags like &lt;div&gt; stay text. Use 2 &gt; 1.</p>
<blockquote><p>Quoted remark from finance.</p></blockquote>
<hr/>
<p><ac:placeholder>Template hint that is not visible</ac:placeholder></p>
<h2></h2>
</ac:layout-cell></ac:layout-section></ac:layout>
"""

CHILD = """<h2>Refund steps</h2>
<p>Refunds go back to the <a href="https://wiki.example.com/wiki/spaces/FIN/pages/1001/Billing+overview">billing overview</a> rules.</p>
<pre>plain preformatted
  text block</pre>
"""

RENDERED = """<html><head><title>Browser tab title</title><style>p{color:red}</style></head><body>
<div class="wiki-content"><h2 id="x">Rendered view</h2>
<p>Text with <a href="/wiki/spaces/FIN/pages/1001/Billing+overview">a page link</a> and
<img class="emoticon emoticon-tick" alt="(tick)" src="/images/tick.png"/> and <img src="https://cdn.example.com/chart.png" alt="chart"/>.</p>
<div class="code panel"><pre class="syntaxhighlighter-pre">SELECT 1;</pre></div>
<table><thead><tr><th>K</th><th>V</th></tr></thead><tbody><tr><td>a</td><td><ul><li>one</li><li>two</li></ul></td></tr></tbody></table>
</div></body></html>
"""

TRUNCATED = """<h2>Half a page</h2><table><tbody><tr><td>cell one</td><td>cell tw"""

LOSSY_MD = """---
title: "Lossy"
page_id: "1005"
space_key: "FIN"
parent_id: "1001"
version: "2"
last_modified: ""
source_url: ""
converted_from: "confluence-html"
---

# Lossy

## Kept heading

Only the first sentence survived.
"""

LOSSY_RAW = """<h2>Kept heading</h2><p>Only the first sentence survived.</p>
<h2>Dropped heading</h2><p>This whole second paragraph about quarterly reconciliation deadlines vanished during conversion.</p>
<table><tbody><tr><td>lost</td><td>table</td></tr></tbody></table>
<p><ac:structured-macro ac:name="children"/></p>"""


def run(*args):
    proc = subprocess.run([PY] + [str(a) for a in args], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def rows(manifest):
    with open(manifest, newline="", encoding="utf-8") as f:
        return {r["page_id"]: r for r in csv.DictReader(f)}


FAILED = []


def check(name, cond, detail=""):
    print("%s  %s" % ("ok  " if cond else "FAIL", name))
    if not cond:
        FAILED.append(name)
        if detail:
            print("      " + detail.replace("\n", "\n      "))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="confluence-loop-test-"))
    try:
        base = tmp / "01-confluence-download"
        shutil.copytree(LOOP, base, ignore=shutil.ignore_patterns("raw", "pages", "attachments", "spotcheck",
                                                                "manifest*.csv", "outputs", "__pycache__"))
        shutil.copytree(LOOP.parent / "tools", tmp / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        (base / "raw").mkdir()
        (base / "attachments" / "1001").mkdir(parents=True)
        (base / "raw" / "1001.html").write_text(RICH, encoding="utf-8")
        (base / "raw" / "1002.html").write_text(CHILD, encoding="utf-8")
        (base / "raw" / "1003.html").write_text(TRUNCATED, encoding="utf-8")
        (base / "raw" / "1004.html").write_text("", encoding="utf-8")
        (base / "raw" / "1005.html").write_text(LOSSY_RAW, encoding="utf-8")
        (base / "raw" / "1006.html").write_text(RENDERED, encoding="utf-8")
        (base / "attachments" / "1001" / "billing flow.png").write_bytes(b"png-bytes")
        (base / "attachments" / "1001" / "spec.pdf").write_bytes(b"pdf-bytes")
        (base / "attachments" / "1001" / "_attachments.json").write_text(
            '[{"filename": "billing flow.png", "size": 9}, {"filename": "spec.pdf", "size": 9}]', encoding="utf-8")

        def row(pid, title, parent, n_att="0", empty=""):
            r = dict.fromkeys(COLUMNS, "")
            r.update(page_id=pid, title=title, space_key="FIN", parent_id=parent, type="page", version="2",
                     source_url="https://wiki.example.com/wiki/spaces/FIN/pages/%s" % pid, attachment_count=n_att,
                     empty_body=empty, status="done", attempts="0", raw_path="raw/%s.html" % pid)
            return r

        manifest = base / "manifest.csv"
        with open(manifest, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerow(row("1001", "Billing overview", "", "2"))
            w.writerow(row("1002", "Refund process", "1001"))
            w.writerow(row("1003", "Truncated: page/with*odd chars?", "1001"))
            w.writerow(row("1004", "Empty container", "1001", empty="yes"))
            w.writerow(row("1005", "Lossy", "1001"))
            w.writerow(row("1006", "Rendered page", "1001"))

        code, out = run(base / "verify.py", "--manifest", manifest, "--inventory", "--expected-count", 6, "--roots", "1001")
        check("inventory accepted when count and tree are right", code == 0 and "INVENTORY: ACCEPTED" in out, out)
        code, out = run(base / "verify.py", "--manifest", manifest, "--inventory", "--expected-count", 7, "--roots", "1001")
        check("inventory rejected when the source count differs", code != 0 and "NOT ACCEPTED" in out, out)

        code, out = run(base / "convert.py", "--manifest", manifest, "--ids", "1001,1002,1003,1004,1006")
        check("convert runs", code == 0, out)
        m = rows(manifest)
        check("md_path filled with id and slug", m["1001"]["md_path"] == "pages/1001-billing-overview.md", m["1001"]["md_path"])
        check("odd characters in title give a safe file name",
              m["1003"]["md_path"] == "pages/1003-truncated-page-with-odd-chars.md", m["1003"]["md_path"])
        md = (base / m["1001"]["md_path"]).read_text(encoding="utf-8")
        expectations = {
            "front matter page id": 'page_id: "1001"',
            "title heading": "# Billing overview",
            "bold and italic": "The **billing service** charges customers on the *first business day*",
            "line break kept": "of each month.  \nLate payments",
            "intraword underscores untouched": "order_line_items and snake_case_name",
            "heading with ampersand": "## Rules & limits",
            "user mention": "@user:abc123",
            "nested list": "  - Approval expires after 14 days",
            "inline code": "`level_two`",
            "page link rewritten to local file": "[the refund page](1002-refund-process.md)",
            "link outside the download marked": "[Legal policy](confluence://LEGAL/Legal%20policy)",
            "ordered list": "1. Collect usage\n2. Generate invoice\n3. Send email",
            "task done": "- [x] Migrate tax tables",
            "task open": "- [ ] Review dunning letters",
            "pipe table header": "| Plan | Monthly fee | Notes |",
            "pipe in cell escaped": "Up to 3 users \\| no SSO",
            "two paragraphs in a cell": "Unlimited users<br>Includes SSO",
            "merged cells kept as html table": '<th colspan="2">',
            "rowspan kept": '<td rowspan="2">',
            "code inside a table cell": "```sql\nSELECT rate FROM vat WHERE country = 'GB';\n```",
            "info panel": "> **Info: Cut-off time**\n>\n> Orders after 17:00 CET are billed the next day.",
            "code block with language": "```python\ndef late_fee(amount):",
            "code content not escaped": "# <b>not html</b>",
            "expand title": "**Expand: Historic exceptions**",
            "expand body": "Until 2021 the fee was 2 percent.",
            "status macro": "\\[STATUS: LIVE\\]",
            "jira key kept as text": "BILL-142",
            "toc placeholder": "\\[Confluence macro: toc",
            "jira query placeholder": 'Confluence macro: jira — jqlQuery="project = BILL AND status = Open"',
            "image to local attachment": "![Billing flow](../attachments/1001/billing%20flow.png)",
            "attachment link": "[spec.pdf](../attachments/1001/spec.pdf)",
            "external link": "[vendor docs](https://example.com/docs?a=1&b=2)",
            "date": "2024-03-05",
            "emoticon": ":tick:",
            "angle brackets stay text": "tags like &lt;div> stay text",
            "blockquote": "> Quoted remark from finance.",
            "rule": "---",
        }
        for name, needle in expectations.items():
            check("convert: " + name, needle in md, "expected to find: %r" % needle)
        check("convert: template placeholder text dropped", "Template hint" not in md)
        check("convert: no Confluence tags left", "<ac:" not in md and "<ri:" not in md)
        check("convert: two placeholders counted", m["1001"]["placeholders"] == "2", m["1001"]["placeholders"])
        child = (base / m["1002"]["md_path"]).read_text(encoding="utf-8")
        check("convert: absolute Confluence URL rewritten to local page", "[billing overview](1001-billing-overview.md)" in child, child)
        check("convert: pre block fenced", "```\nplain preformatted\n  text block\n```" in child, child)
        empty = (base / m["1004"]["md_path"]).read_text(encoding="utf-8")
        check("convert: empty page gets an explicit note", "no body content" in empty)

        (base / "pages" / "1005-lossy.md").write_text(LOSSY_MD, encoding="utf-8")
        run(PY and base.parent / "tools" / "manifest.py", "set", manifest, "1005", "md_path=pages/1005-lossy.md")

        code, out = run(base / "verify.py", "--manifest", manifest, "--ids", "1001,1002,1003,1004,1005,1006")
        m = rows(manifest)
        check("verify: faithful rich page is verified", m["1001"]["status"] == "verified", out)
        check("verify: child page is verified", m["1002"]["status"] == "verified", out)
        check("verify: empty page with empty_body=yes is verified", m["1004"]["status"] == "verified", out)
        rendered = (base / m["1006"]["md_path"]).read_text(encoding="utf-8")
        check("convert: rendered HTML page (head skipped, link localised, list in table cell)",
              "Browser tab title" not in rendered and "[a page link](1001-billing-overview.md)" in rendered
              and "| a | - one<br>- two |" in rendered and "![chart](https://cdn.example.com/chart.png)" in rendered, rendered)
        check("verify: rendered HTML page is verified", m["1006"]["status"] == "verified", out)
        check("verify: truncated raw file fails", m["1003"]["status"] == "failed" and "D2" in m["1003"]["notes"], out)
        check("verify: lossy markdown fails on structure", m["1005"]["status"] == "failed" and "C6" in m["1005"]["notes"], out)
        check("verify: lossy markdown fails on text", "C7" in m["1005"]["notes"], m["1005"]["notes"])
        check("verify: missing macro placeholder is caught", "C10" in m["1005"]["notes"], m["1005"]["notes"])
        check("verify: attempts counted", m["1005"]["attempts"] == "1", m["1005"]["attempts"])

        (base / "attachments" / "1001" / "spec.pdf").unlink()
        code, out = run(base / "verify.py", "--manifest", manifest, "--ids", "1001", "--no-update")
        check("verify: missing attachment fails D3 and C8", "FAIL  D3" in out and "FAIL  C8" in out, out)
        check("verify: --no-update leaves the manifest alone", rows(manifest)["1001"]["status"] == "verified")
        (base / "attachments" / "1001" / "spec.pdf").write_bytes(b"pdf-bytes")

        code, out = run(base.parent / "tools" / "manifest.py", "set", manifest, "1001", "status=verified")
        check("manifest.py refuses to set verified by hand", code != 0, out)
        run(base / "verify.py", "--manifest", manifest, "--ids", "1005")
        code, out = run(base / "verify.py", "--manifest", manifest, "--ids", "1005")
        check("third failure escalates to needs_human", rows(manifest)["1005"]["status"] == "needs_human", out)

        code, out = run(base / "verify.py", "--manifest", manifest, "--final", "--expected-count", 6, "--roots", "1001")
        report = (base / "outputs" / "verification-report.md").read_text(encoding="utf-8")
        check("final report says NOT ACCEPTED while rows are open", code != 0 and "RESULT: NOT ACCEPTED" in report, out)
        check("final report lists placeholder macros", "- toc: 1" in report and "- jira: 1" in report, report)
        check("final report lists links outside the download", "confluence://LEGAL/Legal policy" in report, report)

        code, out = run(base / "convert.py", "--manifest", manifest, "--index")
        index = (base / "pages" / "INDEX.md").read_text(encoding="utf-8")
        check("index shows the page tree", "- [Billing overview](1001-billing-overview.md)\n  - [Refund process](1002-refund-process.md)" in index, index)

        (base / "spotcheck").mkdir()
        (base / "spotcheck" / "1002.html").write_text(CHILD.replace("\n", "\n  "), encoding="utf-8")
        code, out = run(base / "verify.py", "--manifest", manifest, "--spot-compare")
        check("spot check passes for an identical re-fetch", code == 0 and "PASS  1002" in out, out)
        (base / "spotcheck" / "1002.html").write_text(CHILD + "<p>new text</p>", encoding="utf-8")
        code, out = run(base / "verify.py", "--manifest", manifest, "--spot-compare")
        check("spot check flags a differing re-fetch", code != 0 and "DIFF  1002" in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILED:
        print("%d TEST(S) FAILED" % len(FAILED))
        sys.exit(1)
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
