from rscforge.parsers import parse_text, parse_value


def normalized(result) -> list[str]:
    return [entry.normalized for entry in result.entries]


def test_hosts_file_with_multiple_hosts() -> None:
    result = parse_text(
        "0.0.0.0 ads.example.com tracker.example.com\n"
        "127.0.0.1 localhost\n"
        "::1 ip6-localhost\n"
    )
    assert normalized(result) == ["ads.example.com", "tracker.example.com"]


def test_comments_and_duplicates() -> None:
    result = parse_text(
        """
        # comment
        ; comment
        // comment
        ! comment
        Example.COM  # inline comment
        example.com
        1.2.3.4/24
        1.2.3.0/24
        """
    )
    assert normalized(result) == ["example.com", "1.2.3.0/24"]


def test_adblock_rules() -> None:
    result = parse_text(
        "||tracker.example.com^\n"
        "@@||allowed.example.com^\n"
        "||ads.example.com^$important\n"
    )
    assert normalized(result) == ["tracker.example.com", "ads.example.com"]


def test_url_and_port() -> None:
    url_entry = parse_value("https://Example.COM/path?x=1")
    assert url_entry is not None
    assert url_entry.normalized == "example.com"

    port_entry = parse_value("example.com:443")
    assert port_entry is not None
    assert port_entry.normalized == "example.com"


def test_wildcard_and_invalid_values() -> None:
    wildcard = parse_value("*.example.com")
    assert wildcard is not None
    assert wildcard.kind == "domain"
    assert wildcard.normalized == "*.example.com"

    assert parse_value("not a domain") is None
    assert parse_value("0.0.0.0") is None
    assert parse_value("*.bad*domain.example") is None


def test_surrounding_punctuation() -> None:
    for raw in ("(example.com)", "example.com,", "[example.com]", "«example.com»"):
        parsed = parse_value(raw)
        assert parsed is not None
        assert parsed.normalized == "example.com"


def test_ipv6_cidr() -> None:
    entry = parse_value("2001:db8::/32")
    assert entry is not None
    assert entry.kind == "cidr"
    assert entry.normalized == "2001:db8::/32"
