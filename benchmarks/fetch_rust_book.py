"""Save chapters of *The Rust Programming Language* as one Markdown file per chapter, from the
docs of a pinned Rust release, so every benchmark run reads exactly the same text.

    python benchmarks/fetch_rust_book.py 4            # -> benchmarks/fixtures/rust-book/ch04.md

Hidden lines of code examples (`fn main() {` wrappers the book folds away) are dropped, as a
reader of the book doesn't see them either. Figures stay as links to the online images.
"""
from __future__ import annotations

import argparse
import html
import re
import textwrap
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

VERSION = "1.98.0"
BASE = f"https://doc.rust-lang.org/{VERSION}/book/"
OUT = Path(__file__).resolve().parent / "fixtures" / "rust-book"


class _ToMarkdown(HTMLParser):
    """The `<main>` part of an mdBook page as Markdown: headings, paragraphs, lists, code."""

    def __init__(self, page_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.url = page_url
        self.out: list[str] = []
        self.buf: list[str] = []
        self.in_main = self.in_pre = False
        self.skip = 0                                 # depth inside hidden ("boring") code
        self.lists: list[str] = []
        self.code_lang = ""

    def _flush(self, prefix: str = "") -> None:
        text = re.sub(r"[ \t]*\n[ \t]*", " ", "".join(self.buf)).strip()
        if text:
            self.out.append(prefix + text)
        self.buf = []

    def handle_starttag(self, tag: str, attrs_list: list) -> None:
        attrs = dict(attrs_list)
        if tag == "main":
            self.in_main = True
        if not self.in_main:
            return
        if self.skip or (tag == "span" and attrs.get("class") == "boring"):
            self.skip += tag == "span"
            return
        if tag in ("h1", "h2", "h3", "h4", "p", "li", "figcaption"):
            self._flush(self._li_prefix() if self.lists and tag == "p" else "")
        if tag == "pre":
            self._flush()
            self.in_pre = True
        elif tag == "code" and self.in_pre:
            cls = attrs.get("class") or ""
            self.code_lang = "rust" if "language-rust" in cls else (
                cls.split("language-")[1].split()[0] if "language-" in cls else "")
        elif tag == "code":
            self.buf.append("`")
        elif tag in ("em", "i"):
            self.buf.append("*")
        elif tag in ("strong", "b"):
            self.buf.append("**")
        elif tag in ("ul", "ol"):
            self.lists.append(tag)
        elif tag == "img":
            alt = " ".join((attrs.get("alt") or "").split())
            src = urllib.request.urljoin(self.url, attrs.get("src") or "")
            self.out.append(f"![{alt}]({src})")

    def _li_prefix(self) -> str:
        return "  " * (len(self.lists) - 1) + ("1. " if self.lists[-1] == "ol" else "- ")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_main:
            return
        if self.skip:
            self.skip -= tag == "span"
            return
        if tag == "main":
            self._flush()
            self.in_main = False
        elif tag in ("h1", "h2", "h3", "h4"):
            self._flush("#" * int(tag[1]) + " ")
        elif tag in ("p", "figcaption"):
            self._flush(self._li_prefix() if self.lists else "")
        elif tag == "li":
            self._flush(self._li_prefix())
        elif tag in ("ul", "ol"):
            self._flush(self._li_prefix())
            self.lists.pop()
        elif tag == "pre":
            code = textwrap.dedent("".join(self.buf)).strip("\n")
            self.out.append(f"```{self.code_lang}\n{code}\n```")
            self.buf, self.in_pre = [], False
        elif tag == "code" and not self.in_pre:
            self.buf.append("`")
        elif tag in ("em", "i"):
            self.buf.append("*")
        elif tag in ("strong", "b"):
            self.buf.append("**")

    def handle_data(self, data: str) -> None:
        if self.in_main and not self.skip:
            self.buf.append(data)


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def chapter_pages(chapter: int) -> list[str]:
    """The page names of one chapter, in book order, from the book's table of contents."""
    toc = _get(BASE + "toc.html")
    return sorted(set(re.findall(rf'(ch{chapter:02d}-\d\d-[a-z0-9-]+\.html)', toc)))


def fetch(chapter: int) -> Path:
    pages = chapter_pages(chapter)
    if not pages:
        raise SystemExit(f"no pages found for chapter {chapter} at {BASE}")
    parts = [f"<!-- The Rust Programming Language, Rust {VERSION}: {BASE} -->"]
    for name in pages:
        p = _ToMarkdown(BASE + name)
        p.feed(_get(BASE + name))
        parts.append("\n\n".join(html.unescape(x) for x in p.out))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ch{chapter:02d}.md"
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("chapters", type=int, nargs="+")
    for ch in ap.parse_args().chapters:
        path = fetch(ch)
        print(f"{path}  ({len(path.read_text(encoding='utf-8').split())} words)")
