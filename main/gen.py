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
import pprint
import pytz
import shutil
import tomlkit


MAIN_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = MAIN_DIR.parent

TEMPLATES_DIR = MAIN_DIR / "templates"
MAIN_TEMPLATE_PATH = TEMPLATES_DIR / "main.html"
WARN_TEMPLATE_PATH = TEMPLATES_DIR / "warn.html"
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
        # content_html = self.md.render(self.content)
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

    @property
    def id(self):
        return self.path.stem.replace(".", "_")

    def get_published_date(self) -> datetime.datetime:
        published = self.metadata.get("published")
        if not published:
            published = datetime.datetime.utcnow().astimezone(LOCAL_TZ)
        else:
            published = dateutil.parser.parse(published)
        return published

    def get_name(self) -> str:
        name = self.metadata.get("name")
        if not name:
            name = self.path.stem.title().replace("_", " ")
        return name

    def publish(self, html_path, published_data=None):
        if not published_data:
            return {
                "name": self.get_name(),
                "published": self.get_published_date().strftime("%Y %B %d"),
                "content_path": str(self.path),
                "output_path": str(html_path),
            }
        else:
            published_data.update({
                "name": self.metadata.get("name") or published_data["name"],
                "published": (
                    self.metadata["published"].strftime("%Y %B %d") if self.metadata.get("published") else None
                ) or published_data["published"],
                "content_path": str(self.path),
                "output_path": str(html_path),
                "republished": datetime.datetime.utcnow().astimezone(LOCAL_TZ).strftime("%Y %B %d"),
            })
        return published_data


def render_fence(self, tokens, idx, options, env):
    token = tokens[idx]
    if token.info == "_Warn":
        with open(WARN_TEMPLATE_PATH, "r") as f:
            warn = f.read()
        text = token.content
        return warn % text
    else:
        return self.renderToken(tokens, idx, options, env)


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
        self.md.add_render_rule("fence", render_fence)

        self.site_config_path = self.content_dir / "site.toml"
        self.site_config = self.get_site_config()

    def get_site_config(self) -> tomlkit.TOMLDocument:
        if self.site_config_path.exists():
            with open(self.site_config_path, "r") as f:
                return tomlkit.load(f)
        else:
            return {}

    def get_articles_to_publish(self) -> list[MdArticle]:
        articles_to_publish = []
        for path in self.content_dir.glob('**/*.md'):
            publish_info = next(
                iter(i for i in self.site_config.get("articles", {}).values() if i.get("content_path") == path),
                None
            )
            if not publish_info or self.republish is True:
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
        try:
            title = self.site_config["config"]["title"]
        except KeyError:
            title = None

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
        get_published = lambda info: dateutil.parser.parse(info["published"])
        publish_data = sorted(self.site_config.get("articles", {}).values(), key=get_published)[-5:]

        get_menu_item = lambda info: {
            "name": info["name"],
            "url": pathlib.Path(info["output_path"]).name
        }
        menu_data = map(get_menu_item, publish_data)
        with open(self.menu_data_path, "w") as f:
            json.dump(list(menu_data), f)

    def get_last_article(self):
        return next(reversed(dict(self.site_config["articles"]).items()), (None, None))

    def publish_articles(self, articles_to_publish: list[MdArticle]):
        self.write_scaffolding()
        self.write_title()

        if "articles" not in self.site_config:
            self.site_config.add("articles", tomlkit.table())

        for md_article in articles_to_publish:
            html_filename = md_article.path.with_suffix(".html").name
            html_path = self.output_dir / html_filename

            if not html_path.exists() or self.republish:
                with open(html_path, "w") as f:
                    f.write(md_article.html)

                published_data = self.site_config["articles"].get(md_article.id)
                new_published_data = md_article.publish(html_path, published_data=published_data)

                _, last_article_table = self.get_last_article()

                self.site_config["articles"][md_article.id] = new_published_data
                if not published_data:
                    # not republished, so set indentation
                    if last_article_table:
                        indent_level = last_article_table.trivia.indent.count(" ")
                    else:
                        indent_level = 2
                    self.site_config["articles"][md_article.id].indent(indent_level)

        with open(self.site_config_path, "w") as f:
            tomlkit.dump(self.site_config, f)

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
