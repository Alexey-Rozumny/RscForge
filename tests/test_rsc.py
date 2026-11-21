from rscforge.rsc import generate_rsc

BASE_SETTINGS = {
    "list_name": "vpn-filter",
    "include_pbr": "false",
    "vpn_gateway": "",
    "routing_table": "vpn-filter",
    "connection_mark": "vpn-filter-con",
    "routing_mark": "vpn-filter",
    "local_networks_list": "local-networks",
    "wildcard_policy": "skip",
}


def entry(
    normalized: str,
    kind: str = "domain",
    comment: str | None = None,
    source_name: str | None = None,
) -> dict:
    return {
        "normalized": normalized,
        "kind": kind,
        "comment": comment,
        "source_name": source_name,
    }


def test_basic_export() -> None:
    content, stats = generate_rsc(
        [
            entry("example.com", source_name="Test list"),
            entry("10.0.0.0/8", kind="cidr", comment="LAN"),
        ],
        BASE_SETTINGS,
    )

    assert stats["exported"] == 2
    assert stats["domains"] == 1
    assert stats["ip_entries"] == 1
    assert 'remove [find list="vpn-filter" comment~"^rscforge:"]' in content
    assert 'add list="vpn-filter" address=example.com comment="rscforge:src=Test list"' in content
    assert 'add list="vpn-filter" address=10.0.0.0/8 comment="rscforge:LAN"' in content
    assert "/ip/firewall/mangle" not in content


def test_wildcard_skip_and_base_domain() -> None:
    content, stats = generate_rsc([entry("*.example.com")], BASE_SETTINGS)
    assert stats["skipped_wildcards"] == 1
    assert "*.example.com" not in content

    content, stats = generate_rsc(
        [entry("*.example.com")],
        {**BASE_SETTINGS, "wildcard_policy": "base-domain"},
    )
    assert stats["skipped_wildcards"] == 0
    assert "address=example.com" in content


def test_wildcard_deduplicates_with_base_domain() -> None:
    _, stats = generate_rsc(
        [entry("*.example.com"), entry("example.com")],
        {**BASE_SETTINGS, "wildcard_policy": "base-domain"},
    )
    assert stats["exported"] == 1
    assert stats["duplicates"] == 1


def test_pbr_block() -> None:
    content, stats = generate_rsc(
        [entry("example.com")],
        {**BASE_SETTINGS, "include_pbr": "true", "vpn_gateway": "10.8.0.1"},
    )

    assert stats["include_pbr"] is True
    assert "/ip/firewall/mangle" in content
    assert 'new-connection-mark="vpn-filter-con"' in content
    assert 'new-routing-mark="vpn-filter"' in content
    assert "/routing/table" in content
    assert 'gateway="10.8.0.1" routing-table="vpn-filter"' in content


def test_pbr_without_gateway_warns_and_skips_route() -> None:
    content, _ = generate_rsc(
        [entry("example.com")],
        {**BASE_SETTINGS, "include_pbr": "true", "vpn_gateway": ""},
    )
    assert "WARNING" in content
    assert "/ip/route" not in content


def test_comment_escaping() -> None:
    content, _ = generate_rsc(
        [entry("example.com", comment='a"b')],
        BASE_SETTINGS,
    )
    assert 'comment="rscforge:a\\"b"' in content

    content, _ = generate_rsc(
        [entry("example.com", comment="cost$5")],
        BASE_SETTINGS,
    )
    assert 'comment="rscforge:cost\\$5"' in content
