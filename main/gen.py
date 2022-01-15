"""
TODO:
 - republish old article
 - write back metadata to article
 - render warning code blocks
"""

import bs4
import datetime
import dateutil.parser
import distutils.dir_util
import frontmatter
import json
import markdown_it
import markdown_it.tree
import pathlib
import pickle
import pytz


MAIN_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = MAIN_DIR.parent

TEMPLATES_DIR = MAIN_DIR / "templates"
MAIN_TEMPLATE_PATH = TEMPLATES_DIR / "main.html"
OUTPUT_TEMPLATE_DIR = TEMPLATES_DIR / "output"

LOCAL_TZ = pytz.timezone("US/Eastern")


def parse_article(md, path):
    with open(path, "r") as f:
        article = frontmatter.load(f, handler=frontmatter.YAMLHandler())
    
    tokens = md.parse(article.content)
    node = markdown_it.tree.SyntaxTreeNode(tokens)
    return article, node


def render_node(md, node):
    return md.renderer.render(node.to_tokens(), md.options, {})


def make_base_soup(md, node):
    with open(MAIN_TEMPLATE_PATH, "r") as f:
        template = f.read()
    soup = bs4.BeautifulSoup(template, "html.parser")

    content = soup.find(id="content")
    content.string.replace_with(bs4.BeautifulSoup(render_node(md, node), "html.parser"))

    return soup


def resolve_article_published(article):
    published = article.metadata.get("published")
    if not published or published == "now":
        published = article["published"] = datetime.datetime.utcnow()
    else:
        published = dateutil.parser.parse(published)
        published = LOCAL_TZ.localize(published, is_dst=None).astimezone(pytz.utc)
    return published


def resolve_article_name(article, path):
    name = article.metadata.get("name")
    if not name:
        name = path.stem.title().replace("_", " ")
    return name


def main(
    content_dir=(PROJECT_ROOT / "content"),
    output_dir=(PROJECT_ROOT / "output"),
    dry_run=False,
):
    if not isinstance(content_dir, pathlib.Path):
        content_dir = pathlib.Path(content_dir)
    assert content_dir.exists(), "No content!"
    if not isinstance(output_dir, pathlib.Path):
        output_dir = pathlib.Path(output_dir)
    menu_data_path = output_dir / "etc" / "menu_data.json"
    publish_cache_path = output_dir / "etc" / "publish_cache.pickle"

    md = markdown_it.MarkdownIt()

    if not publish_cache_path.exists():
        publish_cache = {}
    else:
        with open(publish_cache_path, "rb") as f:
            publish_cache = pickle.load(f)

    publishes = []
    for path in content_dir.glob('**/*.md'):
        if path not in publish_cache:
            article, node = parse_article(md, path)
            soup = make_base_soup(md, node)
            publishes.append((path, article, soup))

    if dry_run:
        print(f"[dry run] to publish: {publishes}")

    elif publishes:
        print(f"to publish: {publishes}")

        if not output_dir.exists():
            distutils.dir_util.copy_tree(str(OUTPUT_TEMPLATE_DIR), str(output_dir))

        for path, article, soup in publishes:
            html_filename = path.with_suffix(".html").name
            html_path = output_dir / html_filename

            if not html_path.exists():
                with open(html_path, "w") as f:
                    f.write(soup.prettify())

            publish_cache[path] = {
                "published": resolve_article_published(article),
                "output": html_path.name,
                "menu_data": {
                    "name": resolve_article_name(article, path),
                    "url": html_path.name,
                }
            }

        with open(publish_cache_path, "wb") as f:
            pickle.dump(publish_cache, f)

        get_published = lambda info: info["published"]
        publish_data = sorted(publish_cache.values(), key=get_published)[-5:]
        menu_data = map(lambda info: info["menu_data"], publish_data)
        with open(menu_data_path, "w") as f:
            json.dump(list(menu_data), f)

    else:
        print("nothing to publish")
