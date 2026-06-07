import os, re, shutil
from datetime import datetime, date as date_type
import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

SITE_DIR = "_site"
POSTS_DIR = "_posts"
LAYOUTS_DIR = "_layouts"
STATIC_DIRS = ["css", "fonts", "js"]

env = Environment(loader=FileSystemLoader(LAYOUTS_DIR), autoescape=select_autoescape())

md = markdown.Markdown(extensions=["fenced_code", "codehilite"])


def parse_front_matter(text):
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, parts[2].strip()


def render_page(content, layout, **kwargs):
    tmpl = env.get_template(f"{layout}.html")
    return tmpl.render(content=content, **kwargs)


def slug_from_filename(filename):
    stem = os.path.splitext(filename)[0]
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    return stem


def build():
    if os.path.exists(SITE_DIR):
        shutil.rmtree(SITE_DIR)

    posts = []
    for fname in sorted(os.listdir(POSTS_DIR)):
        if not fname.endswith((".md", ".markdown")):
            continue
        with open(os.path.join(POSTS_DIR, fname)) as f:
            fm, body = parse_front_matter(f.read())

        html_body = md.convert(body)
        slug = slug_from_filename(fname)
        url = f"/blog/{slug}/"
        dt = fm.get("date")
        if isinstance(dt, datetime):
            date_obj = dt
        elif isinstance(dt, date_type):
            date_obj = datetime(dt.year, dt.month, dt.day)
        elif isinstance(dt, str):
            date_obj = datetime.strptime(dt, "%Y-%m-%d")
        else:
            date_obj = datetime.now()

        post = {
            "title": fm.get("title", "Untitled"),
            "description": fm.get("description", ""),
            "date_xml": date_obj.strftime("%Y-%m-%dT00:00:00+00:00"),
            "date_formatted": date_obj.strftime("%B %d, %Y"),
            "tags": fm.get("tags", []),
            "url": url,
        }

        content = render_page(
            html_body,
            "post",
            page_title=post["title"],
            description=post["description"],
            page_url=url,
            date_xml=post["date_xml"],
            date_formatted=post["date_formatted"],
            tags=post["tags"],
        )
        content = render_page(
            content,
            "default",
            page_title=post["title"],
            description=post["description"],
            page_url=url,
        )

        out_dir = os.path.join(SITE_DIR, "blog", slug)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "index.html"), "w") as f:
            f.write(content)

        posts.append(post)

    posts.reverse()

    pages = [
        (
            "index.html",
            "/",
            {"page_title": None, "description": "just another void pointer"},
        ),
        (
            "blog/index.html",
            "/blog/",
            {"page_title": "Blog", "description": "Blog posts", "posts": posts},
        ),
    ]

    for src_path, url, extra_vars in pages:
        with open(src_path) as f:
            fm, body = parse_front_matter(f.read())

        ctx = {
            "page_title": extra_vars.get("page_title"),
            "description": extra_vars.get("description"),
            "page_url": url,
            "posts": extra_vars.get("posts", []),
        }
        body_tmpl = env.from_string(body)
        rendered = body_tmpl.render(**ctx)
        content = render_page(rendered, "default", **ctx)

        out_path = os.path.join(SITE_DIR, src_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write(content)

    for d in STATIC_DIRS:
        if os.path.exists(d):
            shutil.copytree(d, os.path.join(SITE_DIR, d), dirs_exist_ok=True)

    for f in ["favicon.svg", "favicon.ico"]:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(SITE_DIR, f))

    with open(os.path.join(SITE_DIR, ".nojekyll"), "w"):
        pass

    print(f"Built site to {SITE_DIR}/ — {len(posts)} posts, {len(pages)} pages")


if __name__ == "__main__":
    build()
