"""
Allow-list HTML sanitizer for LLM-generated artifacts (stdlib only, no third-party deps).

Threat model: generated HTML is UNTRUSTED. It is produced by an LLM that reads transcript text
(which may contain prompt-injection) and by whatever the user asked for. We therefore apply
defence in depth -- this sanitizer is layer 1:

  1. Sanitizer (this module): only structural/typographic tags and a small set of attributes
     survive; scripts, event handlers, forms, iframes, objects, remote resources and
     `javascript:` URLs are removed *before the artifact is stored*.
  2. Viewer iframe: `sandbox=""` -> no scripts, no same-origin, no forms, no popups, no
     top-navigation, even if layer 1 were bypassed.
  3. Injected Content-Security-Policy (`default-src 'none'`) inside the iframe document ->
     no network requests, no remote images/fonts/styles, no exfiltration via CSS `url()`.

`sanitize_html()` returns the cleaned document plus a report of what was removed so the
backend can log `artifact_sanitized` events (observability for artifact-rendering issues).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
import re
from typing import Dict, List, Optional, Tuple

ALLOWED_TAGS = frozenset(
    """html head body title style div span p br hr h1 h2 h3 h4 h5 h6 ul ol li dl dt dd table thead tbody
    tfoot tr th td caption colgroup col strong b em i u s small sub sup mark code pre kbd samp blockquote q
    cite abbr a img figure figcaption section article header footer nav main aside details summary
    label time address""".split()
)
VOID_TAGS = frozenset({"br", "hr", "img", "col"})
# Elements removed together with everything inside them.
DROP_WITH_CONTENT = frozenset(
    """script iframe frame frameset object embed applet noscript template svg math form textarea select
    option button audio video source track canvas link base meta xml head_script""".split()
)
# `meta`/`link` are void; they are dropped but have no content to skip.
VOID_DROPPED = frozenset({"meta", "link", "base", "source", "track", "input", "embed"})

GLOBAL_ATTRS = frozenset({"class", "id", "style", "title", "lang", "dir", "role"})
TAG_ATTRS: Dict[str, frozenset] = {
    "a": frozenset({"href"}),
    "img": frozenset({"src", "alt", "width", "height"}),
    "td": frozenset({"colspan", "rowspan", "align", "valign"}),
    "th": frozenset({"colspan", "rowspan", "align", "valign", "scope"}),
    "col": frozenset({"span", "width"}),
    "ol": frozenset({"start", "type"}),
    "details": frozenset({"open"}),
    "time": frozenset({"datetime"}),
    "table": frozenset({"summary"}),
}

_SAFE_HREF = re.compile(r"^(https?:|mailto:|#)", re.IGNORECASE)
_SAFE_DATA_IMG = re.compile(r"^data:image/(png|jpe?g|gif|webp);base64,[a-z0-9+/=\s]+$", re.IGNORECASE)
_CTRL = re.compile(r"[\x00-\x20\x7f-\x9f]+")

_CSS_BANNED = re.compile(
    r"(@import|expression\s*\(|behaviou?r\s*:|-moz-binding|javascript:|vbscript:|</?style|<script|@charset|@namespace)",
    re.IGNORECASE,
)
# url(...) with up to one level of nested parentheses, e.g. url(javascript:alert(1))
_CSS_URL = re.compile(r"url\s*\((?:[^()]|\([^()]*\))*\)", re.IGNORECASE | re.DOTALL)


@dataclass
class SanitizeReport:
    removed_tags: List[str] = field(default_factory=list)
    removed_attrs: List[str] = field(default_factory=list)
    neutralised_css: int = 0

    @property
    def modified(self) -> bool:
        return bool(self.removed_tags or self.removed_attrs or self.neutralised_css)

    def to_dict(self) -> Dict[str, object]:
        return {
            "removed_tags": sorted(set(self.removed_tags)),
            "removed_attrs": sorted(set(self.removed_attrs)),
            "neutralised_css": self.neutralised_css,
        }


def sanitize_css(css: str, report: Optional[SanitizeReport] = None) -> str:
    """Neutralise dangerous constructs in a CSS string (style attribute values or <style> blocks)."""
    original = css

    # 1. Drop whole declarations / at-rules that contain banned constructs.
    parts = re.split(r"(?<=[;{}])", css)
    css = "".join(p for p in parts if not _CSS_BANNED.search(p))

    # 2. Only inline data: images/fonts may be referenced with url(); everything else is removed.
    def _url_repl(m: re.Match) -> str:
        inner = re.sub(r"^url\s*\(\s*['\"]?|['\"]?\s*\)$", "", m.group(0), flags=re.IGNORECASE).strip()
        if _SAFE_DATA_IMG.match(inner) or inner.lower().startswith("data:font/"):
            return m.group(0)
        return "none"

    css = _CSS_URL.sub(_url_repl, css)
    if report is not None and css != original:
        report.neutralised_css += 1
    return css


def _clean_attr(tag: str, name: str, value: Optional[str], report: SanitizeReport) -> Optional[str]:
    name = name.lower()
    allowed = GLOBAL_ATTRS | TAG_ATTRS.get(tag, frozenset())
    if not (name in allowed or name.startswith("aria-")):
        report.removed_attrs.append(f"{tag}[{name}]")
        return None
    if value is None:
        value = ""
    if name == "href":
        compact = _CTRL.sub("", value)
        if not _SAFE_HREF.match(compact):
            report.removed_attrs.append(f"{tag}[href]")
            return None
        return value
    if name == "src":
        compact = value.strip()
        if not _SAFE_DATA_IMG.match(compact):
            report.removed_attrs.append(f"{tag}[src]")
            return None
        return compact
    if name == "style":
        return sanitize_css(value, report)
    return value


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.stack: List[str] = []
        self.skip_depth = 0
        self.skip_tag: Optional[str] = None
        self.in_style = False
        self.report = SanitizeReport()

    # -- tags -----------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.report.removed_tags.append(tag)
            if tag not in VOID_DROPPED:
                self.skip_depth, self.skip_tag = 1, tag
            return
        if tag not in ALLOWED_TAGS:
            self.report.removed_tags.append(tag)  # unknown tag: drop the tag, keep its text
            return

        rendered = []
        for name, value in attrs:
            cleaned = _clean_attr(tag, name, value, self.report)
            if cleaned is not None:
                rendered.append(f' {name.lower()}="{escape(cleaned, quote=True)}"')
        if tag == "img" and not any(a.startswith(" src=") for a in rendered):
            return  # image without a safe (data:) source is useless; drop it
        self.out.append(f"<{tag}{''.join(rendered)}>")
        if tag == "style":
            self.in_style = True
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS and self.stack and self.stack[-1] == tag.lower():
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.skip_depth:
            if tag == self.skip_tag:
                self.skip_depth -= 1
                if self.skip_depth == 0:
                    self.skip_tag = None
            return
        if tag not in ALLOWED_TAGS or tag in VOID_TAGS or tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            self.out.append(f"</{top}>")
            if top == "style":
                self.in_style = False
            if top == tag:
                break

    # -- text -----------------------------------------------------------------
    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.in_style:
            self.out.append(sanitize_css(data, self.report))
        else:
            self.out.append(escape(data, quote=False))

    def handle_comment(self, data: str) -> None:  # comments are dropped (IE conditional-comment tricks)
        return

    def handle_decl(self, decl: str) -> None:
        return

    def handle_pi(self, data: str) -> None:
        return

    def unknown_decl(self, data: str) -> None:
        return

    def close_open_tags(self) -> None:
        while self.stack:
            top = self.stack.pop()
            self.out.append(f"</{top}>")


def sanitize_html(raw_html: str) -> Tuple[str, SanitizeReport]:
    """Return (clean_html, report). Input may be a fragment or a full document."""
    parser = _Sanitizer()
    parser.feed(raw_html or "")
    parser.close()
    parser.close_open_tags()
    return "".join(parser.out).strip(), parser.report


DEFAULT_DOC_STYLE = """
body{font-family:Georgia,'Times New Roman',serif;line-height:1.7;max-width:760px;margin:0 auto;padding:32px 24px;
background:#0c0d0e;color:#e5e7eb}h1,h2,h3{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#fff;line-height:1.25}
a{color:#38bdf8}blockquote{border-left:3px solid #f59e0b;margin:1em 0;padding-left:1em;color:#9da3ae;font-style:italic}
code,pre{background:#1c1f22;border-radius:4px;padding:2px 6px}table{border-collapse:collapse}td,th{border:1px solid #25292e;padding:6px 10px}
""".strip()


def wrap_document(clean_fragment: str, title: str = "Artifact") -> str:
    """Ensure the sanitized output is a complete HTML document."""
    lowered = clean_fragment.lower()
    if "<html" in lowered:
        return "<!DOCTYPE html>\n" + clean_fragment
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{escape(title)}</title><style>{DEFAULT_DOC_STYLE}</style></head>"
        f"<body>{clean_fragment}</body></html>"
    )
