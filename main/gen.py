"""
TODO:
 - render warning code blocks
 - serialize published MdArticle to human-readable format?
"""

import bs4
import dataclasses
import datetime
import dateutil.parser
import frontmatter
import json
import markdown_it
import markdown_it.token
import markdown_it.tree
import pathlib
import pickle
import pprint
import pytz
import shutil
import toml


MAIN_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = MAIN_DIR.parent

TEMPLATES_DIR = MAIN_DIR / "templates"
MAIN_TEMPLATE_PATH = TEMPLATES_DIR / "main.html"
OUTPUT_TEMPLATE_DIR = TEMPLATES_DIR / "output"

LOCAL_TZ = pytz.timezone("US/Eastern")


@dataclasses.dataclass
class MdArticle:
    md: markdown_it.MarkdownIt = dataclasses.field(repr=False)
    path: pathlib.Path

    def __post_init__(self):
        # dataclass hook, runs after __init__
        self.metadata, self.content = self.parse_file()
        md_tokens = self.parse_md()
        content_html = self.render_md(md_tokens)
        self.html = self.render(content_html)

    def parse_file(self) -> tuple[dict, str]:
        with open(self.path, "r") as f:
            fm_article = frontmatter.load(f, handler=frontmatter.YAMLHandler())
        return fm_article.metadata, fm_article.content

    def parse_md(self) -> list[markdown_it.token.Token]:
        md_tokens = self.md.parse(self.content)
        # md_node = markdown_it.tree.SyntaxTreeNode(md_tokens)
        # md_tokens = md_node.to_tokens()
        return md_tokens

    def render_md(self, md_tokens: list[markdown_it.token.Token]) -> str:
        return self.md.renderer.render(md_tokens, self.md.options, {})

    def render(self, content_html: str) -> str:
        with open(MAIN_TEMPLATE_PATH, "r") as f:
            template = f.read()
        soup = bs4.BeautifulSoup(template, "html.parser")

        content = soup.find(id="content")
        content.string.replace_with(
            bs4.BeautifulSoup(
                content_html,
                "html.parser"
            )
        )

        return soup.prettify()

    def get_published_date(self) -> datetime.datetime:
        published = self.metadata.get("published")
        if not published or published == "now":
            published = datetime.datetime.utcnow()
        else:
            published = dateutil.parser.parse(published)
            published = LOCAL_TZ.localize(published, is_dst=None).astimezone(pytz.utc)
        return published

    def get_name(self) -> str:
        name = self.metadata.get("name")
        if not name:
            name = self.path.stem.title().replace("_", " ")
        return name


@dataclasses.dataclass
class SiteGenerator:
    content_dir: pathlib.Path | str
    output_dir: pathlib.Path | str
    republish: bool = False

    def __post_init__(self):
        # dataclass hook, runs after __init__
        if not isinstance(self.content_dir, pathlib.Path):
            self.content_dir = pathlib.Path(self.content_dir)
        assert self.content_dir.exists(), "No content!"

        if not isinstance(self.output_dir, pathlib.Path):
            self.output_dir = pathlib.Path(self.output_dir)

        self.menu_data_path = self.output_dir / "etc" / "menu_data.json"
        self.md = markdown_it.MarkdownIt()
        self.publish_cache_path = self.output_dir / "publish_cache.pickle"
        self.publish_cache = self.get_publish_cache()

    def get_publish_cache(self) -> dict:
        if not self.publish_cache_path.exists() or self.republish:
            publish_cache = {}
        else:
            with open(self.publish_cache_path, "rb") as f:
                publish_cache = pickle.load(f)
        return publish_cache

    def get_articles_to_publish(self) -> list[MdArticle]:
        articles_to_publish = []
        for path in self.content_dir.glob('**/*.md'):
            if path not in self.publish_cache or self.republish is True:
                article = MdArticle(self.md, path)
                if not article.metadata.get("draft"):
                    articles_to_publish.append(article)

        return articles_to_publish

    def write_scaffolding(self):
        if not self.output_dir.exists():
            shutil.copytree(OUTPUT_TEMPLATE_DIR, self.output_dir)
        else:
            for template_file in OUTPUT_TEMPLATE_DIR.iterdir():
                target_file = self.output_dir / template_file.name
                if template_file.is_file():
                    shutil.copyfile(template_file, target_file)
                else:
                    if target_file.exists():
                        shutil.rmtree(target_file)
                    shutil.copytree(template_file, target_file)

    def write_title(self):
        site_config_file = self.content_dir / "site.toml"
        title = None
        if site_config_file.exists():
            with open(site_config_file, "r") as f:
                try:
                    title = toml.load(f)["config"]["title"]
                except KeyError:
                    pass

        if title:
            output_index_file = self.output_dir / "index.html"
            assert output_index_file.exists()

            with open(output_index_file, "r") as f:
                html = f.read()
            soup = bs4.BeautifulSoup(html, "html.parser")

            title_value = soup.find(id="title-value")
            title_value.string.replace_with(title)

            with open(output_index_file, "w") as f:
                f.write(soup.prettify())

    def write_menu_data(self):
        get_published = lambda info: info["published"]
        publish_data = sorted(self.publish_cache.values(), key=get_published)[-5:]

        get_menu_item = lambda info: {"name": info["name"], "url": info["output_path"].name}
        menu_data = map(get_menu_item, publish_data)
        with open(self.menu_data_path, "w") as f:
            json.dump(list(menu_data), f)

    def publish_articles(self, articles_to_publish: list[MdArticle]):
        self.write_scaffolding()
        self.write_title()

        for md_article in articles_to_publish:
            html_filename = md_article.path.with_suffix(".html").name
            html_path = self.output_dir / html_filename

            if not html_path.exists() or self.republish:
                with open(html_path, "w") as f:
                    f.write(md_article.html)

                self.publish_cache[md_article.path] = {
                    "output_path": html_path,
                    "published": md_article.get_published_date(),
                    "name": md_article.get_name(),
                }

        with open(self.publish_cache_path, "wb") as f:
            pickle.dump(self.publish_cache, f)

        self.write_menu_data()


def main(
    content_dir: (pathlib.Path | str) = (PROJECT_ROOT / "content"),
    output_dir: (pathlib.Path | str) = (PROJECT_ROOT / "output"),
    dry_run: bool = False,
    republish: bool = False,
):
    site_generator = SiteGenerator(content_dir, output_dir, republish=republish)
    articles_to_publish = site_generator.get_articles_to_publish()

    if dry_run:
        print("[dry run] to publish:")
        pprint.pprint(articles_to_publish)

    elif articles_to_publish:
        print("to publish:")
        pprint.pprint(articles_to_publish)
        site_generator.publish_articles(articles_to_publish)

    else:
        print("nothing to publish")
