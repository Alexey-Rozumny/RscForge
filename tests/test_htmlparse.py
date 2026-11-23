import asyncio

import pytest

from rscforge import services
from rscforge.htmlparse import looks_like_html, parse_html
from rscforge.services import SourceFetchError, _zerum_endpoint


def normalized(result) -> list[str]:
    return [entry.normalized for entry in result.entries]


def test_html_ignores_navigation_scripts_and_assets() -> None:
    html = """
    <!doctype html>
    <html>
      <head>
        <script>var fake = "evil.example";</script>
        <link href="../site/style.css" rel="stylesheet">
      </head>
      <body>
        <nav>
          <a href="home.html">Home</a>
          <a href="list.html">List</a>
        </nav>
        <ul>
          <li>vk.com</li>
          <li>advisor.wmtransfer.com</li>
        </ul>
        <a href="https://blocked.example/path">link</a>
        <p>Node.js и style.css — это не домены.</p>
      </body>
    </html>
    """

    values = normalized(parse_html(html, "https://provider.example/ua/list.html"))

    assert "vk.com" in values
    assert "advisor.wmtransfer.com" in values
    assert "blocked.example" in values
    assert "home.html" not in values
    assert "list.html" not in values
    assert "evil.example" not in values
    assert "node.js" not in values
    assert "style.css" not in values


def test_html_fragment_from_ajax() -> None:
    fragment = (
        '<li class="item">vk.com <span class="badge">заборонений</span></li>'
        '<li class="item">82.fskn.ru <span class="badge">заборонений</span></li>'
    )

    assert normalized(parse_html(fragment)) == ["vk.com", "82.fskn.ru"]


def test_looks_like_html() -> None:
    assert looks_like_html("<!DOCTYPE html><html></html>")
    assert looks_like_html("plain text", "text/html; charset=utf-8")
    assert not looks_like_html("example.com\n1.2.3.4")


def test_zerum_endpoint_detection() -> None:
    html = """
    <script>
      var wp = '../zerum/';
      var ajax_path = wp + "php/site_ajax.php";
    </script>
    <div pagtemplate="uacheck_sitelist_pag"></div>
    """

    assert _zerum_endpoint("https://checkprovider.in.ua/ua/list.html", html) == (
        "https://checkprovider.in.ua/zerum/php/site_ajax.php",
        "uacheck_sitelist_pag",
    )


def test_zerum_endpoint_rejects_foreign_origin() -> None:
    html = """
    <script>
      var wp = 'https://evil.example/';
      var ajax_path = wp + "site_ajax.php";
    </script>
    <div pagtemplate="list"></div>
    """

    assert _zerum_endpoint("https://provider.example/ua/list.html", html) is None


def test_parse_url_uses_html_parser(monkeypatch) -> None:
    html = (
        '<html><body><a href="home.html">Home</a>'
        "blocked.example</body></html>"
    )

    async def fake_read_url(url: str):
        return html, "text/html; charset=utf-8"

    async def fake_read_zerum(url: str, text: str):
        return None

    monkeypatch.setattr(services, "_read_url", fake_read_url)
    monkeypatch.setattr(services, "_read_zerum", fake_read_zerum)

    result = asyncio.run(services._parse_url("https://provider.example/list.html"))

    assert [entry.normalized for entry in result.entries] == ["blocked.example"]


def test_parse_url_raises_when_zerum_expansion_fails(monkeypatch) -> None:
    html = (
        '<script>var wp = "../zerum/"; '
        'var ajax_path = wp + "site_ajax.php";</script>'
        '<div pagtemplate="list"></div>'
    )

    async def fake_read_url(url: str):
        return html, "text/html"

    async def fake_read_zerum(url: str, text: str):
        return None

    monkeypatch.setattr(services, "_read_url", fake_read_url)
    monkeypatch.setattr(services, "_read_zerum", fake_read_zerum)

    with pytest.raises(SourceFetchError):
        asyncio.run(services._parse_url("https://provider.example/list.html"))
