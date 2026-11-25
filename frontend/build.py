#!/usr/bin/env python3
"""Build the site.

    content/*.tex  --(make4ht)-->  frontend/public/generated/*.html
                   --(converter)--> semantic HTML fragments
                   --(jinja2)---->  dist/

The LaTeX documents are the source of truth for content. The frontend shell
in src/ owns layout, navigation and the terminal look.
"""

import argparse
import functools
import hashlib
import html as html_lib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"
CONTENT = ROOT / "content"
GENERATED = FRONTEND / "public" / "generated"
BUILD = ROOT / ".build" / "latex"
DIST = ROOT / "dist"

SITE_URL = "https://fr4nsyz.github.io"
MEDIA_DIRS = ["img", "videos", "music", "assets", "fonts"]
STATIC_FILES = ["favicon.svg", "favicon.ico"]
STATE_FILE = ROOT / ".build" / "build-state.json"
STATE_VERSION = 1

DOCUMENT_RE = re.compile(r"\\begin\{document\}")
INCLUDE_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
META_RE = re.compile(r"\\newcommand\{\\Doc(\w+)\}\{(.*?)\}\s*$", re.M)
DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
IMAGE_RE = re.compile(r"\\webimgw?\{([^}]*)\}\{([^}]*)\}")


def log(message):
    print(message)


def file_signature(path):
    stat = path.stat()
    return hashlib.sha256(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()


def dependency_signature(path, seen=None):
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen:
        return ""
    seen.add(path)
    parts = [file_signature(path)]
    source = path.read_text(encoding="utf-8")
    for name in INCLUDE_RE.findall(source):
        candidates = []
        if name.endswith(".tex"):
            candidates.append(path.parent / name)
            candidates.append(CONTENT / name)
        else:
            candidates.append(path.parent / f"{name}.tex")
            candidates.append(CONTENT / name)
            candidates.append(CONTENT / f"{name}.tex")
        for candidate in candidates:
            if candidate.exists():
                parts.append(dependency_signature(candidate, seen))
                break
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def load_state():
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if state.get("version") != STATE_VERSION:
        return {}
    return state


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 1 - compile the LaTeX sources
# ---------------------------------------------------------------------------


def find_documents():
    """Every .tex file under content/ that is a complete document."""
    documents = []
    for path in sorted(CONTENT.rglob("*.tex")):
        source = path.read_text(encoding="utf-8")
        if DOCUMENT_RE.search(source):
            documents.append((path, source))
    return documents


def parse_metadata(source):
    metadata = {}
    for match in META_RE.finditer(source):
        metadata[match.group(1).lower()] = match.group(2).strip()
    return metadata


def slug_for(path):
    match = DATE_PREFIX_RE.match(path.stem)
    return match.group(2) if match else path.stem


def date_for(path):
    match = DATE_PREFIX_RE.match(path.stem)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def compile_latex(path, slug):
    """Compile one document with make4ht and return the raw HTML."""
    work = BUILD / slug
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copy2(path, work / f"{slug}.tex")

    env = os.environ.copy()
    env["TEXINPUTS"] = f"{CONTENT}{os.pathsep}{work}{os.pathsep}"

    proc = subprocess.run(
        ["make4ht", f"{slug}.tex"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )

    html_file = work / f"{slug}.html"
    if not html_file.exists():
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"latex: failed to compile {path}")

    log_file = work / f"{slug}.log"
    if log_file.exists():
        errors = [
            line
            for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.startswith("! ")
        ]
        if errors:
            sys.stderr.write("\n".join(errors) + "\n")
            raise SystemExit(f"latex: {path} reported {len(errors)} error(s)")

    return html_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 2 - turn the tex4ht output into clean HTML fragments
# ---------------------------------------------------------------------------

SPAN_RE = re.compile(r"<(/?)span\b([^>]*)>", re.I)
CLASS_RE = re.compile(r"class=['\"]([^'\"]*)['\"]")

FONT_TAGS = {
    "cmtt": "code",
    "ec-lmtt": "code",
    "cmbx": "strong",
    "ec-lmbx": "strong",
    "cmti": "em",
    "ec-lmti": "em",
    "cmsl": "em",
    "ec-lmsl": "em",
}

HEADING_TAGS = {
    "sectionHead": "h2",
    "likesectionHead": "h2",
    "subsectionHead": "h3",
    "likesubsectionHead": "h3",
    "subsubsectionHead": "h4",
    "chapterHead": "h2",
    "likechapterHead": "h2",
    "appendixHead": "h2",
}


def extract_body(document):
    match = re.search(r"<body[^>]*>(.*)</body>", document, re.S)
    return match.group(1) if match else document


def font_tag(class_name):
    for prefix, tag in FONT_TAGS.items():
        if class_name.startswith(prefix):
            return tag
    return None


def rewrite_font_spans(fragment):
    """\\texttt, \\textbf and \\textit become <code>, <strong> and <em>."""
    out = []
    stack = []
    pos = 0
    for match in SPAN_RE.finditer(fragment):
        out.append(fragment[pos : match.start()])
        pos = match.end()
        if match.group(1) == "":
            class_match = CLASS_RE.search(match.group(2))
            tag = font_tag(class_match.group(1)) if class_match else None
            out.append(match.group(0))
            stack.append((tag, len(out) - 1))
        else:
            if stack:
                tag, index = stack.pop()
                if tag:
                    out[index] = f"<{tag}>"
                    out.append(f"</{tag}>")
                    continue
            out.append(match.group(0))
    out.append(fragment[pos:])
    return "".join(out)


HEADING_RE = re.compile(r"<h([2-6])([^>]*)>|</h([2-6])>", re.I)


def rewrite_headings(fragment):
    """Sections become h2/h3/h4 and lose their numbering."""
    out = []
    stack = []
    pos = 0
    for match in HEADING_RE.finditer(fragment):
        out.append(fragment[pos : match.start()])
        pos = match.end()
        if match.group(3):
            if stack:
                out.append(f"</{stack.pop()}>")
                continue
            out.append(match.group(0))
            continue
        class_match = CLASS_RE.search(match.group(2))
        tag = HEADING_TAGS.get(class_match.group(1)) if class_match else None
        if tag:
            out.append(f"<{tag}>")
            stack.append(tag)
        else:
            out.append(match.group(0))
    out.append(fragment[pos:])
    fragment = "".join(out)
    fragment = re.sub(r"<span class='titlemark'>.*?</span>", "", fragment, flags=re.S)
    return fragment


def render_code(code, language):
    lexer = None
    if language:
        try:
            lexer = get_lexer_by_name(language)
        except ClassNotFound:
            lexer = None
    if lexer is None:
        if not code.strip():
            lexer = TextLexer()
        else:
            try:
                lexer = guess_lexer(code)
            except ClassNotFound:
                lexer = TextLexer()
    formatter = HtmlFormatter(nowrap=True)
    highlighted = highlight(code, lexer, formatter)
    return '<div class="codehilite"><pre>' + highlighted + "</pre></div>"


def rewrite_code_blocks(fragment):
    """Verbatim blocks become syntax highlighted code blocks."""
    token_re = re.compile(
        r"<!--\s*lang:([A-Za-z0-9_+#.-]+)\s*-->|<pre class='verbatim'[^>]*>(.*?)</pre>",
        re.S,
    )
    out = []
    pos = 0
    language = None
    for match in token_re.finditer(fragment):
        out.append(fragment[pos : match.start()])
        pos = match.end()
        if match.group(1):
            language = match.group(1).lower()
            continue
        code = html_lib.unescape(match.group(2) or "").replace("\xa0", " ")
        out.append(render_code(code.strip("\n"), language))
        language = None
    out.append(fragment[pos:])
    return "".join(out)


def rewrite_tables(fragment):
    """tex4ht tables become plain tables whose first row is a header."""
    fragment = re.sub(
        r"<div class='tabular'>\s*(<table class='tabular'.*?</table>)\s*</div>",
        r"\1",
        fragment,
        flags=re.S,
    )

    def fix(match):
        table = match.group(0)
        table = re.sub(r"<colgroup.*?</colgroup>", "", table, flags=re.S)
        table = re.sub(r"<col\b[^>]*>", "", table)
        table = re.sub(r"<tr class='hline'>.*?</tr>", "", table, flags=re.S)
        for row in re.finditer(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = row.group(1)
            if not re.search(r"<td[^>]*>\s*\S", cells):
                continue
            header = re.sub(r"<td([^>]*)>", r"<th\1>", cells).replace("</td>", "</th>")
            table = table[: row.start(1)] + header + table[row.end(1) :]
            break
        return table

    return re.sub(r"<table class='tabular'.*?</table>", fix, fragment, flags=re.S)


def clean_classes(fragment):
    fragment = re.sub(r"<ul class='itemize\d*'>", "<ul>", fragment)
    fragment = re.sub(r"<ol class='enumerate\d*'>", "<ol>", fragment)
    fragment = re.sub(r"<li class='itemize'>", "<li>", fragment)
    fragment = re.sub(r"<li class='enumerate'[^>]*>", "<li>", fragment)
    fragment = re.sub(r"<p class=['\"](?:noindent|indent|nopar)['\"]\s*>", "<p>", fragment)
    fragment = re.sub(r"<br class='newline'\s*/>", "<br/>", fragment)
    fragment = re.sub(r"(<(?:p|h[2-6])[^>]*>)\s+", r"\1", fragment)
    return fragment


def strip_tex_ids(fragment):
    fragment = re.sub(r"<a\s+id=['\"]x1-[^'\"]*['\"]></a>", "", fragment)
    fragment = re.sub(
        r"\s+id=['\"](?:x1-|TBL-|verbatim-|listing-|fancyvrb)[^'\"]*['\"]", "", fragment
    )
    fragment = re.sub(
        r"(<(?:td|th|tr|table)\b[^>]*?)\s+style='[^']*'", r"\1", fragment
    )
    return fragment


def strip_empty_paragraphs(fragment):
    previous = None
    while previous != fragment:
        previous = fragment
        fragment = re.sub(r"<p[^>]*>\s*</p>\s*", "", fragment)
    return fragment


def straighten_quotes(fragment):
    """LaTeX quotes become straight quotes, like the old Markdown site."""
    parts = re.split(r'(<div class="codehilite"><pre>.*?</pre></div>)', fragment, flags=re.S)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = (
                part.replace("’", "'")
                .replace("‘", "'")
                .replace("“", '"')
                .replace("”", '"')
            )
    return "".join(parts)


def convert(document):
    """tex4ht output -> a semantic HTML fragment."""
    fragment = extract_body(document)
    fragment = strip_line_comments(fragment)
    fragment = rewrite_code_blocks(fragment)
    fragment = rewrite_headings(fragment)
    fragment = rewrite_font_spans(fragment)
    fragment = rewrite_tables(fragment)
    fragment = clean_classes(fragment)
    fragment = strip_tex_ids(fragment)
    fragment = strip_empty_paragraphs(fragment)
    fragment = straighten_quotes(fragment)
    return fragment.strip()


def strip_line_comments(fragment):
    return re.sub(r"<!--\s*l\.\s*\d+\s*-->", "", fragment)


# ---------------------------------------------------------------------------
# Stage 3 - render the shell
# ---------------------------------------------------------------------------


def absolute_url(src):
    if src.startswith(("http://", "https://", "//")):
        return src
    return SITE_URL + "/" + src.lstrip("/")


def first_image(source):
    match = IMAGE_RE.search(source)
    if not match:
        return None, None
    return absolute_url(match.group(1).strip()), match.group(2).strip() or None


def make_environment():
    return Environment(loader=FileSystemLoader(str(SRC)), autoescape=True)


def render(env, template, context):
    return env.get_template(template).render(**context)


def build_pages(env, fragments, posts):
    all_tags = sorted({tag for post in posts for tag in post["tags"]})

    index_context = {
        "page_title": None,
        "description": "just another void pointer",
        "page_url": "/",
        "fragments": fragments,
    }
    pages = {
        "index.html": render(
            env,
            "layouts/default.html.j2",
            {
                **index_context,
                "content": render(env, "pages/index.html.j2", index_context),
            },
        )
    }

    blog_context = {
        "page_title": "Blog",
        "description": "Blog posts",
        "page_url": "/blog/",
        "posts": posts,
        "all_tags": all_tags,
    }
    pages["blog/index.html"] = render(
        env,
        "layouts/default.html.j2",
        {**blog_context, "content": render(env, "pages/blog-index.html.j2", blog_context)},
    )

    for post in posts:
        context = {
            "page_title": post["title"],
            "description": post["description"],
            "page_url": post["url"],
            "date_xml": post["date_xml"],
            "date_formatted": post["date_formatted"],
            "tags": post["tags"],
            "image": post["image"],
            "image_alt": post["image_alt"],
            "content": post["fragment"],
        }
        pages[f"blog/{post['slug']}/index.html"] = render(
            env,
            "layouts/default.html.j2",
            {**context, "content": render(env, "layouts/post.html.j2", context)},
        )

    return pages


def static_sources():
    sources = {}
    for relative in ("styles/style.css", "js/shell.js"):
        target = "css/style.css" if relative.startswith("styles") else "js/shell.js"
        sources[target] = SRC / relative
    for directory in MEDIA_DIRS:
        source_dir = ROOT / directory
        if source_dir.exists():
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    sources[f"{directory}/{path.relative_to(source_dir).as_posix()}"] = path
    for name in STATIC_FILES:
        source = ROOT / name
        if source.exists():
            sources[name] = source
    return sources


def copy_static_incremental(state):
    old = state.get("static", {})
    current = {}
    for relative, source in static_sources().items():
        signature = file_signature(source)
        current[relative] = signature
        target = DIST / relative
        if old.get(relative) == signature and target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        log(f"static: {relative}")
    for relative in old:
        if relative not in current:
            target = DIST / relative
            if target.exists():
                target.unlink()
                log(f"static: removed {relative}")
    (DIST / ".nojekyll").write_text("")
    state["static"] = current


def copy_static():
    DIST.mkdir(parents=True, exist_ok=True)
    for relative in ("styles/style.css", "js/shell.js"):
        target = DIST / ("css/style.css" if relative.startswith("styles") else "js/shell.js")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC / relative, target)
    for directory in MEDIA_DIRS:
        source = ROOT / directory
        if source.exists():
            shutil.copytree(source, DIST / directory, dirs_exist_ok=True)
    for name in STATIC_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, DIST / name)
    (DIST / ".nojekyll").write_text("")


def build(content_only=False, incremental=False):
    state = load_state() if incremental else {}
    use_incremental = incremental and bool(state)

    if use_incremental:
        GENERATED.mkdir(parents=True, exist_ok=True)
        if not content_only:
            DIST.mkdir(parents=True, exist_ok=True)
    else:
        if not content_only and DIST.exists():
            shutil.rmtree(DIST)
        if GENERATED.exists():
            shutil.rmtree(GENERATED)
        GENERATED.mkdir(parents=True, exist_ok=True)

    fragments = {}
    posts = []
    manifest = {"pages": {}, "posts": []}
    documents_state = {}
    old_documents = state.get("documents", {})
    current_slugs = set()

    for path, source in find_documents():
        slug = slug_for(path)
        current_slugs.add(slug)
        metadata = parse_metadata(source)
        relative = path.relative_to(CONTENT)
        output = (
            GENERATED / "blog" / f"{slug}.html"
            if relative.parent.name == "blog"
            else GENERATED / f"{slug}.html"
        )
        output_name = str(output.relative_to(GENERATED))
        signature = dependency_signature(path)
        cached = old_documents.get(slug)

        if (
            use_incremental
            and cached
            and cached.get("signature") == signature
            and cached.get("output") == output_name
            and output.exists()
        ):
            fragment = output.read_text(encoding="utf-8")
        else:
            fragment = convert(compile_latex(path, slug))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(fragment, encoding="utf-8")
            log(f"latex: {relative} -> {output.relative_to(GENERATED)}")

        documents_state[slug] = {"signature": signature, "output": output_name}

        if relative.parent.name == "blog":
            date = date_for(path)
            image, image_alt = first_image(source)
            post = {
                "slug": slug,
                "title": metadata.get("title", "Untitled"),
                "description": metadata.get("description", ""),
                "tags": [tag.strip() for tag in metadata.get("tags", "").split(",") if tag.strip()],
                "url": f"/blog/{slug}/",
                "date_xml": date.strftime("%Y-%m-%dT00:00:00+00:00") if date else "",
                "date_formatted": date.strftime("%B %d, %Y") if date else "",
                "image": image,
                "image_alt": image_alt,
                "fragment": fragment,
            }
            posts.append(post)
            manifest["posts"].append({k: v for k, v in post.items() if k != "fragment"})
        else:
            fragments[slug] = fragment
            manifest["pages"][slug] = {"fragment": output_name}

    for slug, cached in old_documents.items():
        output_name = cached.get("output")
        if slug not in current_slugs and output_name:
            output = GENERATED / output_name
            if output.exists() and output.is_file():
                output.unlink()
                log(f"latex: removed {output_name}")

    posts.sort(key=lambda post: post["date_xml"], reverse=True)
    manifest["posts"] = posts
    (GENERATED / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if content_only:
        log(f"Compiled {len(fragments)} fragments and {len(posts)} posts to {GENERATED.relative_to(ROOT)}/")
        return

    env = make_environment()
    pages = build_pages(env, fragments, posts)

    for name, html in pages.items():
        target = DIST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")

    if use_incremental:
        copy_static_incremental(state)
    else:
        copy_static()
        state["static"] = {
            relative: file_signature(source) for relative, source in static_sources().items()
        }

    state["version"] = STATE_VERSION
    state["documents"] = documents_state
    save_state(state)

    verb = "Updated" if use_incremental else "Built"
    log(f"{verb} site to {DIST.relative_to(ROOT)}/ - {len(posts)} posts, {len(pages)} pages")


def watch_snapshot():
    snapshot = {}
    for path in CONTENT.rglob("*.tex"):
        snapshot[str(path)] = file_signature(path)
    for path in SRC.rglob("*"):
        if path.is_file():
            snapshot[str(path)] = file_signature(path)
    for source in static_sources().values():
        snapshot[str(source)] = file_signature(source)
    return snapshot


def watch(port):
    build(incremental=True)

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

    handler = functools.partial(QuietHandler, directory=str(DIST))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log(f"Serving dist/ on http://localhost:{port}/")

    last = watch_snapshot()
    try:
        while True:
            time.sleep(0.75)
            current = watch_snapshot()
            if current == last:
                continue
            changed = sorted(path for path, signature in current.items() if last.get(path) != signature)
            removed = sorted(path for path in last if path not in current)
            labels = changed + [f"{path} (removed)" for path in removed]
            last = current
            names = [str(Path(path).relative_to(ROOT)) for path in labels[:8]]
            log("changed: " + ", ".join(names))
            build(incremental=True)
    except KeyboardInterrupt:
        log("stopping")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the site from the LaTeX sources.")
    parser.add_argument(
        "--content-only",
        action="store_true",
        help="compile the LaTeX sources and stop before rendering the shell",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="rebuild only changed documents and static files",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="rebuild changed files and serve dist locally",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="port for --watch",
    )
    args = parser.parse_args()

    if args.watch:
        watch(args.port)
    else:
        build(content_only=args.content_only, incremental=args.incremental)
