#!/usr/bin/env python3
"""Convert downloaded Confluence page bodies to Markdown. Standard library only.

Input : raw/<page_id>.html   (Confluence storage format, or rendered "view" HTML)
        raw/<page_id>.md     (only if the connector can return nothing but Markdown)
Output: pages/<page_id>-<slug>.md   one Markdown file per Confluence page

Usage:
  python convert.py --manifest manifest.csv --ids 123,456
  python convert.py --manifest manifest.csv --status done
  python convert.py --manifest manifest.csv --all
  python convert.py --manifest manifest.csv --index      # writes pages/INDEX.md (page tree)

All paths in the manifest are relative to the folder that contains the manifest.
The script fills `md_path` and `placeholders` in the manifest for every page it converts.
It never changes `status`.
"""
import argparse
import html
import json
import os
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from manifest import read_manifest, write_manifest  # noqa: E402

VOID = {"br", "hr", "img", "col", "input", "meta", "link", "wbr", "area", "base", "embed", "source", "track", "param"}
SKIP = {"script", "style", "head", "title", "ac:parameter", "ac:placeholder", "ac:task-id", "ac:task-uuid",
        "ac:task-status", "colgroup"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
BLOCK_TAGS = set(HEADINGS) | {
    "p", "ul", "ol", "table", "pre", "blockquote", "hr", "div", "section", "article", "header", "footer",
    "main", "figure", "details", "dl", "ac:layout", "ac:layout-section", "ac:layout-cell", "ac:task-list",
    "ac:rich-text-body", "ac:adf-extension", "ac:adf-node", "ac:adf-content", "ac:adf-fallback",
}
MACRO_TAGS = {"ac:structured-macro", "ac:macro"}
PANELS = {"info": "Info", "note": "Note", "warning": "Warning", "tip": "Tip", "panel": "Panel",
          "success": "Success", "error": "Error"}
TRANSPARENT_MACROS = {"excerpt", "details", "section", "column", "layout", "layout-section", "layout-cell"}
BR = "\x00BR\x00"


# ----------------------------------------------------------------------------- tree

class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = {k: (v if v is not None else "") for k, v in (attrs or [])}
        self.children = []

    def kids(self, tag=None):
        return [c for c in self.children if isinstance(c, Node) and (tag is None or c.tag == tag)]

    def child(self, tag):
        for c in self.children:
            if isinstance(c, Node) and c.tag == tag:
                return c
        return None

    def descendants(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                for d in c.descendants():
                    yield d

    def text(self):
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.text())
        return "".join(out)


class TreeBuilder(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def expand_cdata(raw):
    """Turn CDATA sections into escaped text so every Python version parses them the same way."""
    return re.sub(r"<!\[CDATA\[(.*?)\]\]>", lambda m: html.escape(m.group(1), quote=False), raw, flags=re.S)


def parse(raw):
    builder = TreeBuilder()
    builder.feed(expand_cdata(raw))
    builder.close()
    return builder.root


# ----------------------------------------------------------------------------- helpers

def slugify(title, maxlen=60):
    s = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].strip("-") or "page"


def md_name(row):
    return "%s-%s.md" % (row["page_id"], slugify(row.get("title", "")))


def esc(text):
    text = text.replace("\\", "\\\\")
    text = re.sub(r"([*`\[\]])", r"\\\1", text)
    text = re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", r"\\_", text)
    text = re.sub(r"<(?=[A-Za-z/!?])", "&lt;", text)
    return text


def wrap(mark, s):
    core = s.strip()
    if not core or core == BR:
        return s
    lead = s[: len(s) - len(s.lstrip())]
    trail = s[len(s.rstrip()):]
    return "%s%s%s%s%s" % (lead, mark, core, mark, trail)


def fence(body, lang=""):
    body = body.replace("\r\n", "\n").strip("\n")
    longest = max([len(m) for m in re.findall(r"`+", body)] or [0])
    ticks = "`" * max(3, longest + 1)
    return "%s%s\n%s\n%s" % (ticks, lang, body, ticks)


def code_span(text):
    text = re.sub(r"\s+", " ", text)
    longest = max([len(m) for m in re.findall(r"`+", text)] or [0])
    ticks = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return "%s%s%s%s%s" % (ticks, pad, text, pad, ticks)


def guard_line_starts(text):
    out = []
    for line in text.split("\n"):
        if re.match(r"(#{1,6}\s|[-+]\s|\d+[.)]\s|>|={3,}\s*$|-{3,}\s*$)", line):
            line = "\\" + line
        out.append(line)
    return "\n".join(out)


def quote_block(text):
    return "\n".join((">" if not line else "> " + line) for line in text.split("\n"))


def indent_block(text, marker):
    pad = " " * len(marker)
    lines = text.split("\n")
    return "\n".join([marker + lines[0]] + [(pad + line if line else "") for line in lines[1:]])


def span_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


# ----------------------------------------------------------------------------- converter

class Converter:
    def __init__(self, row, by_title, by_id):
        self.row = row
        self.page_id = row["page_id"]
        self.space = row.get("space_key", "")
        self.by_title = by_title
        self.by_id = by_id
        self.placeholders = 0
        self.warnings = []
        parts = urlsplit(row.get("source_url", "") or "")
        self.base = "%s://%s" % (parts.scheme, parts.netloc) if parts.scheme and parts.netloc else ""

    # ---- macros

    def macro_name(self, node):
        return (node.attrs.get("ac:name") or "").lower()

    def macro_params(self, node):
        params = {}
        for p in node.kids("ac:parameter"):
            name = p.attrs.get("ac:name", "")
            value = " ".join(p.text().split())
            if not value:
                for d in p.descendants():
                    if d.tag.startswith("ri:"):
                        value = (d.attrs.get("ri:content-title") or d.attrs.get("ri:filename")
                                 or d.attrs.get("ri:value") or d.attrs.get("ri:space-key") or "")
                        break
            params[name] = value
        return params

    def macro_is_block(self, node):
        return node.child("ac:rich-text-body") is not None or node.child("ac:plain-text-body") is not None

    def placeholder(self, name, params):
        self.placeholders += 1
        shown = ", ".join('%s="%s"' % (k or "value", v) for k, v in params.items() if v)
        return "\\[Confluence macro: %s%s\\]" % (esc(name), (" — " + esc(shown)) if shown else "")

    def inline_macro(self, node, ctx):
        name = self.macro_name(node)
        params = self.macro_params(node)
        if name == "anchor":
            return ""
        if name == "status":
            return "\\[STATUS: %s\\]" % esc(params.get("title") or params.get("colour") or "")
        if name == "jira" and params.get("key"):
            return esc(params["key"])
        text = self.placeholder(name or "unnamed", params)
        for d in node.descendants():
            if d.tag == "ri:attachment" and d.attrs.get("ri:filename"):
                fname = d.attrs["ri:filename"]
                text += " [%s](%s)" % (esc(fname), self.attachment_path(d))
                break
        return text

    def block_macro(self, node, ctx):
        name = self.macro_name(node)
        params = self.macro_params(node)
        title = params.get("title", "")
        plain = node.child("ac:plain-text-body")
        rich = node.child("ac:rich-text-body")
        out = []
        if plain is not None:
            if title:
                out.append("**%s**" % esc(title))
            lang = params.get("language", "") if name == "code" else ("" if name in ("noformat", "code") else name)
            out.append(fence(plain.text(), lang))
            return out
        body = self.blocks(rich.children, ctx) if rich is not None else []
        if name in PANELS:
            label = "**%s%s**" % (PANELS[name], (": " + esc(title)) if title else "")
            return [quote_block("\n\n".join([label] + body))]
        if name == "expand":
            return ["**Expand: %s**" % esc(title or "details")] + body
        if name in TRANSPARENT_MACROS:
            return (["**%s**" % esc(title)] if title else []) + body
        shown = ", ".join('%s="%s"' % (k or "value", v) for k, v in params.items() if v)
        label = "**\\[Confluence macro: %s%s\\]**" % (esc(name or "unnamed"), (" — " + esc(shown)) if shown else "")
        return [label] + body

    # ---- links and images

    def page_target(self, title, space):
        row = self.by_title.get((space or self.space, title)) or self.by_title.get(("", title))
        if row is not None:
            return md_name(row)
        return "confluence://%s/%s" % (quote(space or self.space or "-"), quote(title or "", safe=""))

    def attachment_path(self, ri_attachment):
        fname = ri_attachment.attrs.get("ri:filename", "")
        owner = self.page_id
        other = ri_attachment.child("ri:page")
        if other is not None:
            row = self.by_title.get((other.attrs.get("ri:space-key") or self.space, other.attrs.get("ri:content-title", "")))
            if row is not None:
                owner = row["page_id"]
        return "../attachments/%s/%s" % (owner, quote(fname))

    def ac_link(self, node, ctx):
        body = node.child("ac:plain-text-link-body")
        rich = node.child("ac:link-body")
        if body is not None:
            text = esc(" ".join(body.text().split()))
        elif rich is not None:
            text = self.inline(rich.children, ctx).strip()
        else:
            text = ""
        anchor = node.attrs.get("ac:anchor", "")
        frag = ("#" + quote(anchor)) if anchor else ""
        user = node.child("ri:user")
        if user is not None:
            ident = user.attrs.get("ri:account-id") or user.attrs.get("ri:userkey") or user.attrs.get("ri:username") or ""
            return text or ("@user:%s" % ident)
        page = node.child("ri:page") or node.child("ri:blog-post")
        if page is not None:
            title = page.attrs.get("ri:content-title", "")
            target = self.page_target(title, page.attrs.get("ri:space-key", ""))
            return "[%s](%s%s)" % (text or esc(title), target, frag)
        entity = node.child("ri:content-entity")
        if entity is not None:
            cid = entity.attrs.get("ri:content-id", "")
            row = self.by_id.get(cid)
            target = md_name(row) if row is not None else "confluence://id/%s" % cid
            return "[%s](%s%s)" % (text or esc((row or {}).get("title", "") or cid), target, frag)
        att = node.child("ri:attachment")
        if att is not None:
            fname = att.attrs.get("ri:filename", "")
            return "[%s](%s)" % (text or esc(fname), self.attachment_path(att))
        space = node.child("ri:space")
        if space is not None:
            key = space.attrs.get("ri:space-key", "")
            return "[%s](confluence://%s/)" % (text or esc(key), quote(key))
        url = node.child("ri:url")
        if url is not None:
            value = url.attrs.get("ri:value", "")
            return "[%s](%s)" % (text or esc(value), value)
        if anchor:
            return "[%s](%s)" % (text or esc(anchor), frag)
        return text

    def html_link(self, node, ctx):
        href = node.attrs.get("href", "")
        text = self.inline(node.children, ctx).strip()
        if not href:
            return text
        target = href
        m = re.search(r"/pages/(\d+)|[?&]pageId=(\d+)", href)
        if m:
            row = self.by_id.get(m.group(1) or m.group(2))
            if row is not None:
                frag = urlsplit(href).fragment
                target = md_name(row) + (("#" + frag) if frag else "")
        if target == href and href.startswith("/") and self.base:
            target = self.base + href
        target = target.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
        return "[%s](%s)" % (text or esc(href), target)

    def image(self, node):
        if node.tag == "ac:image":
            alt = node.attrs.get("ac:alt") or node.attrs.get("ac:title") or ""
            att = node.child("ri:attachment")
            url = node.child("ri:url")
            if att is not None:
                return "![%s](%s)" % (esc(alt or att.attrs.get("ri:filename", "")), self.attachment_path(att))
            if url is not None:
                return "![%s](%s)" % (esc(alt), url.attrs.get("ri:value", ""))
            self.warnings.append("image without a source")
            return "![%s]()" % esc(alt)
        src = node.attrs.get("src", "")
        alt = node.attrs.get("alt", "")
        if "emoticon" in node.attrs.get("class", ""):
            return esc(alt or node.attrs.get("data-emoticon-name", ""))
        m = re.search(r"/download/(?:attachments|thumbnails)/(\d+)/([^?#]+)", src)
        if m and m.group(1) in self.by_id:
            src = "../attachments/%s/%s" % (m.group(1), m.group(2))
        elif src.startswith("/") and self.base:
            src = self.base + src
        return "![%s](%s)" % (esc(alt), src.replace(" ", "%20"))

    # ---- inline

    def is_block(self, node):
        if node.tag in MACRO_TAGS:
            return self.macro_is_block(node)
        return node.tag in BLOCK_TAGS

    def inline(self, children, ctx):
        out = []
        for c in children:
            if isinstance(c, str):
                out.append(esc(re.sub(r"\s+", " ", c)))
                continue
            tag = c.tag
            if tag in SKIP:
                continue
            if tag == "br":
                out.append(BR)
            elif tag in ("strong", "b"):
                out.append(wrap("**", self.inline(c.children, ctx)))
            elif tag in ("em", "i"):
                out.append(wrap("*", self.inline(c.children, ctx)))
            elif tag in ("s", "del", "strike"):
                out.append(wrap("~~", self.inline(c.children, ctx)))
            elif tag in ("code", "tt", "kbd", "samp"):
                text = c.text()
                out.append(code_span(text) if text.strip() else "")
            elif tag in ("sub", "sup"):
                inner = self.inline(c.children, ctx)
                out.append("<%s>%s</%s>" % (tag, inner, tag) if inner.strip() else inner)
            elif tag == "a":
                out.append(self.html_link(c, ctx))
            elif tag == "ac:link":
                out.append(self.ac_link(c, ctx))
            elif tag in ("ac:image", "img"):
                out.append(self.image(c))
            elif tag == "ac:emoticon":
                out.append(c.attrs.get("ac:emoji-fallback") or (":%s:" % c.attrs.get("ac:name", "emoji")))
            elif tag == "time":
                out.append(esc(c.attrs.get("datetime", "") or c.text()))
            elif tag in MACRO_TAGS:
                if self.macro_is_block(c):
                    out.append("\n\n" + "\n\n".join(self.block_macro(c, ctx)) + "\n\n")
                else:
                    out.append(self.inline_macro(c, ctx))
            elif self.is_block(c):
                out.append("\n\n" + "\n\n".join(self.block(c, ctx)) + "\n\n")
            else:
                if tag.startswith(("ac:", "ri:")) and tag not in ("ac:inline-comment-marker", "ac:link-body"):
                    if tag.startswith("ri:"):
                        continue
                    self.warnings.append("unhandled tag rendered as plain content: %s" % tag)
                out.append(self.inline(c.children, ctx))
        return "".join(out)

    def finish_inline(self, text, ctx):
        """Collapse spaces, resolve line breaks, and protect line starts."""
        parts = [re.sub(r"[ \t]+", " ", p).strip(" ") for p in text.split(BR)]
        while parts and not parts[-1].strip():
            parts.pop()
        while parts and not parts[0].strip():
            parts.pop(0)
        if not parts:
            return ""
        joined = ("<br>" if ctx.get("cell") else "  \n").join(parts)
        if "\n\n" in joined:  # a block element was embedded in inline content
            return re.sub(r"\n{3,}", "\n\n", joined).strip("\n")
        return guard_line_starts(joined)

    # ---- blocks

    def blocks(self, children, ctx):
        out = []
        run = []

        def flush():
            if run:
                text = self.finish_inline(self.inline(run, ctx), ctx)
                if text.strip():
                    out.append(text)
                del run[:]

        for c in children:
            if isinstance(c, str):
                if c.strip() or run:
                    run.append(c)
                continue
            if c.tag in SKIP:
                continue
            if self.is_block(c):
                flush()
                out.extend(self.block(c, ctx))
            else:
                run.append(c)
        flush()
        return [b for b in out if b.strip()]

    def block(self, node, ctx):
        tag = node.tag
        if tag in MACRO_TAGS:
            return self.block_macro(node, ctx)
        if tag in HEADINGS:
            text = self.finish_inline(self.inline(node.children, dict(ctx, cell=True)), dict(ctx, cell=True))
            text = text.replace("<br>", " ").strip()
            if text.startswith("\\") and len(text) > 1 and text[1] in "#-+>=0123456789":
                text = text[1:]
            return ["%s %s" % ("#" * HEADINGS[tag], text)] if text else []
        if tag == "p":
            if any(isinstance(c, Node) and self.is_block(c) for c in node.children):
                return self.blocks(node.children, ctx)
            text = self.finish_inline(self.inline(node.children, ctx), ctx)
            return [text] if text.strip() else []
        if tag in ("ul", "ol"):
            return [self.list_block(node, ctx, ordered=(tag == "ol"))]
        if tag == "ac:task-list":
            return [self.task_list(node, ctx)]
        if tag == "table":
            table = self.table(node, ctx)
            return [table] if table else []
        if tag == "pre":
            return [fence(node.text())]
        if tag == "blockquote":
            inner = self.blocks(node.children, ctx)
            return [quote_block("\n\n".join(inner))] if inner else []
        if tag == "hr":
            return ["---"]
        if tag == "dl":
            items = []
            for c in node.kids():
                text = self.finish_inline(self.inline(c.children, ctx), ctx)
                if text:
                    items.append(("**%s**" % text) if c.tag == "dt" else (": " + text))
            return ["\n".join(items)] if items else []
        return self.blocks(node.children, ctx)

    def join_item(self, blocks):
        text = ""
        for i, b in enumerate(blocks):
            if i == 0:
                text = b
            elif re.match(r"(- |\d+\. )", b):
                text += "\n" + b
            else:
                text += "\n\n" + b
        return text

    def list_block(self, node, ctx, ordered):
        lines = []
        n = span_int(node.attrs.get("start")) if ordered else 1
        for li in node.kids():
            if li.tag != "li":
                if li.tag in ("ul", "ol") and lines:  # malformed: nested list not wrapped in <li>
                    lines.append(indent_block(self.list_block(li, ctx, li.tag == "ol"), "  ").replace("  ", "  ", 1))
                continue
            marker = "%d. " % n if ordered else "- "
            content = self.join_item(self.blocks(li.children, ctx)) or ""
            lines.append(indent_block(content, marker))
            n += 1
        return "\n".join(lines)

    def task_list(self, node, ctx):
        lines = []
        for task in node.kids("ac:task"):
            status = task.child("ac:task-status")
            done = status is not None and status.text().strip().lower() == "complete"
            body = task.child("ac:task-body")
            content = self.join_item(self.blocks(body.children, ctx)) if body is not None else ""
            lines.append(indent_block(content, "- [x] " if done else "- [ ] "))
        return "\n".join(lines)

    def table_rows(self, table):
        rows = []
        for c in table.kids():
            if c.tag == "tr":
                rows.append(c)
            elif c.tag in ("thead", "tbody", "tfoot"):
                rows.extend(c.kids("tr"))
        return rows

    def table(self, node, ctx):
        rows = [[c for c in tr.kids() if c.tag in ("th", "td")] for tr in self.table_rows(node)]
        rows = [r for r in rows if r]
        if not rows:
            return ""
        complex_table = False
        for r in rows:
            for cell in r:
                if span_int(cell.attrs.get("colspan")) > 1 or span_int(cell.attrs.get("rowspan")) > 1:
                    complex_table = True
                for d in cell.descendants():
                    if d.tag in HEADINGS or d.tag in ("table", "pre") or (d.tag in MACRO_TAGS and self.macro_is_block(d)):
                        complex_table = True
        if complex_table:
            return self.html_table(rows, ctx)
        cell_ctx = dict(ctx, cell=True)
        rendered = []
        for r in rows:
            cells = []
            for cell in r:
                text = "<br>".join(b.replace("\n", "<br>") for b in self.blocks(cell.children, cell_ctx))
                text = text.replace("|", "\\|").strip()
                if cell.tag == "th" and rendered and text:
                    text = "**%s**" % text
                cells.append(text)
            rendered.append(cells)
        width = max(len(r) for r in rendered)
        rendered = [r + [""] * (width - len(r)) for r in rendered]
        header_is_first = all(c.tag == "th" for c in rows[0])
        header = rendered[0] if header_is_first else [""] * width
        body = rendered[1:] if header_is_first else rendered
        lines = ["| " + " | ".join(header) + " |", "|" + "|".join([" --- "] * width) + "|"]
        lines += ["| " + " | ".join(r) + " |" for r in body]
        return "\n".join(lines)

    def html_table(self, rows, ctx):
        out = ["<table>"]
        for r in rows:
            out.append("<tr>")
            for cell in r:
                attrs = "".join(' %s="%d"' % (k, span_int(cell.attrs.get(k)))
                                for k in ("colspan", "rowspan") if span_int(cell.attrs.get(k)) > 1)
                inner = self.blocks(cell.children, dict(ctx, cell=False))
                if inner:
                    out.append("<%s%s>\n\n%s\n\n</%s>" % (cell.tag, attrs, "\n\n".join(inner), cell.tag))
                else:
                    out.append("<%s%s></%s>" % (cell.tag, attrs, cell.tag))
            out.append("</tr>")
        out.append("</table>")
        return "\n".join(out)

    def convert(self, raw):
        root = parse(raw)
        body = root
        for d in root.descendants():  # rendered HTML may be a full document
            if d.tag == "body":
                body = d
                break
        return "\n\n".join(self.blocks(body.children, {}))


# ----------------------------------------------------------------------------- files

def front_matter(row, converted_from):
    keys = ["title", "page_id", "space_key", "parent_id", "version", "last_modified", "source_url"]
    lines = ["---"]
    for k in keys:
        lines.append("%s: %s" % (k, json.dumps(row.get(k, "") or "", ensure_ascii=False)))
    lines.append("converted_from: %s" % json.dumps(converted_from))
    lines.append("---")
    return "\n".join(lines)


def convert_row(row, base, by_title, by_id):
    raw_path = row.get("raw_path", "")
    if not raw_path:
        return {"page_id": row["page_id"], "error": "raw_path is empty; fetch the page first"}
    src = base / raw_path
    if not src.exists():
        return {"page_id": row["page_id"], "error": "raw file not found: %s" % raw_path}
    raw = src.read_text(encoding="utf-8", errors="replace")
    conv = Converter(row, by_title, by_id)
    if src.suffix.lower() == ".md":
        body, kind = raw.strip(), "connector-markdown"
        if re.match(r"#\s", body):
            title_line = ""
        else:
            title_line = "# %s\n\n" % esc(row.get("title", ""))
    else:
        body, kind = conv.convert(raw), "confluence-html"
        title_line = "# %s\n\n" % esc(row.get("title", ""))
    if not body.strip():
        body = "*(This page has no body content in Confluence.)*"
    rel = "pages/" + md_name(row)
    dst = base / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("%s\n\n%s%s\n" % (front_matter(row, kind), title_line, body), encoding="utf-8")
    row["md_path"] = rel
    if "placeholders" in row:
        row["placeholders"] = str(conv.placeholders)
    return {"page_id": row["page_id"], "md_path": rel, "placeholders": conv.placeholders,
            "warnings": sorted(set(conv.warnings))}


def build_index(rows, base):
    ids = {r["page_id"] for r in rows}
    children = {}
    for r in rows:
        parent = r.get("parent_id", "") if r.get("parent_id", "") in ids else ""
        children.setdefault(parent, []).append(r)
    lines = ["# Page index", "", "Every Confluence page in the download, in its original tree.", ""]

    def walk(parent, depth):
        for r in children.get(parent, []):
            name = md_name(r)
            if (base / "pages" / name).exists():
                item = "[%s](%s)" % (esc(r.get("title", "")), name)
            else:
                item = "%s *(no local file yet: %s)*" % (esc(r.get("title", "")), r.get("status", ""))
            lines.append("%s- %s" % ("  " * depth, item))
            walk(r["page_id"], depth + 1)

    walk("", 0)
    (base / "pages").mkdir(parents=True, exist_ok=True)
    (base / "pages" / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", required=True)
    p.add_argument("--ids", help="comma-separated page ids")
    p.add_argument("--status", help="convert every row with this status")
    p.add_argument("--all", action="store_true", help="convert every row that has a raw_path")
    p.add_argument("--index", action="store_true", help="write pages/INDEX.md")
    a = p.parse_args()

    manifest = Path(a.manifest).resolve()
    base = manifest.parent
    fields, rows = read_manifest(str(manifest))
    by_id = {r["page_id"]: r for r in rows}
    by_title = {}
    for r in rows:
        by_title[(r.get("space_key", ""), r.get("title", ""))] = r
        by_title.setdefault(("", r.get("title", "")), r)

    if a.index:
        print(json.dumps({"index": "pages/INDEX.md", "pages": build_index(rows, base)}))
        return

    if a.ids:
        wanted = [i.strip() for i in a.ids.split(",") if i.strip()]
        missing = [i for i in wanted if i not in by_id]
        if missing:
            sys.exit("Not in manifest: %s" % ", ".join(missing))
        targets = [by_id[i] for i in wanted]
    elif a.status:
        targets = [r for r in rows if r.get("status") == a.status]
    elif a.all:
        targets = [r for r in rows if r.get("raw_path")]
    else:
        sys.exit("Give one of --ids, --status, --all, --index")

    errors = 0
    for row in targets:
        result = convert_row(row, base, by_title, by_id)
        errors += 1 if "error" in result else 0
        print(json.dumps(result, ensure_ascii=False))
    write_manifest(str(manifest), fields, rows)
    print("converted=%d errors=%d" % (len(targets) - errors, errors), file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
