from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

DOMAIN_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
DOMAIN_RE = re.compile(rf"^(?:{DOMAIN_LABEL}\.)+(?:[a-z]{{2,63}}|xn--[a-z0-9-]{{2,59}})$")

SKIP_DOMAINS = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "ip6-localhost",
    "ip6-loopback",
    "local",
}

LINE_COMMENT_PREFIXES = ("#", ";", "//", "!")


@dataclass(frozen=True)
class ParsedEntry:
    value: str
    normalized: str
    kind: str
    comment: str | None = None


@dataclass
class ParseResult:
    entries: list[ParsedEntry] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def domains(self) -> int:
        return sum(1 for entry in self.entries if entry.kind == "domain")

    @property
    def ip_entries(self) -> int:
        return sum(1 for entry in self.entries if entry.kind in {"ip", "cidr"})


def _parse_ip(value: str) -> ParsedEntry | None:
    try:
        if "/" in value:
            network = ipaddress.ip_network(value, strict=False)
            return ParsedEntry(value=value, normalized=str(network), kind="cidr")
        address = ipaddress.ip_address(value)
        if str(address) in {"0.0.0.0", "::"}:
            return None
        return ParsedEntry(value=value, normalized=str(address), kind="ip")
    except ValueError:
        return None


def _parse_domain(value: str) -> ParsedEntry | None:
    value = (
        value.strip()
        .strip("\"'()[]{}<>,;«»")
        .strip()
        .rstrip(".")
        .lower()
    )
    if not value:
        return None

    wildcard = False
    if value.startswith("*."):
        wildcard = True
        value = value[2:]
    elif "*" in value:
        return None

    value = value.lstrip(".")
    if not value or value in SKIP_DOMAINS:
        return None

    if "/" in value:
        value = value.split("/", 1)[0]
    if ":" in value and value.count(":") == 1:
        host, _, port = value.partition(":")
        if port.isdigit():
            value = host

    if not value.isascii():
        try:
            value = value.encode("idna").decode("ascii")
        except UnicodeError:
            return None

    if not DOMAIN_RE.match(value):
        return None

    display = f"*.{value}" if wildcard else value
    return ParsedEntry(value=display, normalized=display, kind="domain")


def parse_value(raw: str) -> ParsedEntry | None:
    """Parse a single token (domain, IP, CIDR, URL or AdBlock rule)."""
    value = raw.strip().strip("\"'").strip()
    if not value:
        return None

    low = value.lower()
    if low.startswith(("http://", "https://")):
        host = urlsplit(value).hostname
        if not host:
            return None
        return _parse_ip(host) or _parse_domain(host)

    parsed = _parse_ip(value)
    if parsed:
        return parsed

    if value.startswith("@@"):
        return None
    if value.startswith("||"):
        value = value[2:]
    elif value.startswith("|"):
        value = value[1:]

    if "^" in value:
        value = value.split("^", 1)[0]
    if "$" in value:
        value = value.split("$", 1)[0]

    # dnsmasq-style: address=/example.com/0.0.0.0
    if value.startswith("address=/"):
        parts = value.split("/")
        if len(parts) >= 2:
            value = parts[1]

    return _parse_domain(value)


def _hosts_targets(line: str) -> list[str]:
    """Return hostnames from a hosts-file line like '0.0.0.0 example.com'."""
    parts = line.split()
    if len(parts) < 2:
        return []
    try:
        ipaddress.ip_address(parts[0])
    except ValueError:
        return []
    return parts[1:]


def parse_text(text: str) -> ParseResult:
    entries: list[ParsedEntry] = []
    skipped: list[str] = []
    seen: set[str] = set()

    def add(parsed: ParsedEntry | None, raw: str) -> None:
        if parsed is None:
            if raw and raw not in skipped and len(skipped) < 200:
                skipped.append(raw)
            return
        if parsed.normalized in seen:
            return
        seen.add(parsed.normalized)
        entries.append(parsed)

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        if line.startswith(LINE_COMMENT_PREFIXES):
            continue

        for marker in ("#", ";"):
            index = line.find(marker)
            if index != -1:
                line = line[:index]
        index = line.find(" //")
        if index != -1:
            line = line[:index]
        line = line.strip()
        if not line:
            continue

        targets = _hosts_targets(line)
        if targets:
            for target in targets:
                add(parse_value(target), target)
            continue

        for token in re.split(r"[,\s]+", line):
            token = token.strip()
            if token:
                add(parse_value(token), token)

    return ParseResult(entries=entries, skipped=skipped)
