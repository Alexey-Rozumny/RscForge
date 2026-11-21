from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone

COMMENT_PREFIX = "rscforge:"


def _as_bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _quote(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def _clean_comment(value: str) -> str:
    value = re.sub(r"[\r\n]+", " ", value).strip()
    return value[:100]


def _comment(entry: dict) -> str:
    label = (entry.get("comment") or "").strip()
    if not label:
        source = (entry.get("source_name") or "").strip()
        label = f"src={source}" if source else "manual"
    return f"{COMMENT_PREFIX}{_clean_comment(label)}"


def _ip_sort_key(entry: dict) -> tuple:
    try:
        network = ipaddress.ip_network(entry["normalized"], strict=False)
        return (network.version, int(network.network_address), network.prefixlen)
    except ValueError:
        return (9, 0, 0)


def generate_rsc(entries: list[dict], settings: dict[str, str]) -> tuple[str, dict]:
    list_name = (settings.get("list_name") or "vpn-filter").strip()
    include_pbr = _as_bool(settings.get("include_pbr"))
    wildcard_policy = settings.get("wildcard_policy") or "skip"

    vpn_gateway = (settings.get("vpn_gateway") or "").strip()
    routing_mark = (settings.get("routing_mark") or list_name).strip()
    routing_table = (settings.get("routing_table") or routing_mark).strip()
    connection_mark = (settings.get("connection_mark") or f"{list_name}-con").strip()
    local_networks = (settings.get("local_networks_list") or "local-networks").strip()

    exported: list[tuple[str, dict]] = []
    seen: set[str] = set()
    skipped_wildcards = 0
    duplicates = 0

    for entry in entries:
        normalized = entry["normalized"]
        if normalized.startswith("*."):
            if wildcard_policy != "base-domain":
                skipped_wildcards += 1
                continue
            normalized = normalized[2:]
            if not normalized:
                skipped_wildcards += 1
                continue
        if normalized in seen:
            duplicates += 1
            continue
        seen.add(normalized)
        exported.append((normalized, entry))

    domains = sorted(
        ((address, entry) for address, entry in exported if entry["kind"] == "domain"),
        key=lambda item: item[0],
    )
    ip_entries = sorted(
        ((address, entry) for address, entry in exported if entry["kind"] != "domain"),
        key=lambda item: _ip_sort_key({"normalized": item[0]}),
    )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = [
        "# RscForge export",
        f"# generated: {now}",
        f"# list: {list_name}",
        f"# entries: {len(exported)} (domains: {len(domains)}, ip/cidr: {len(ip_entries)})",
    ]
    if skipped_wildcards:
        lines.append(f"# skipped wildcard domains: {skipped_wildcards}")
    if include_pbr and not vpn_gateway:
        lines.append("# WARNING: PBR enabled, but vpn_gateway is empty — route was not generated")
    lines.append("")

    lines.append("/ip/firewall/address-list")
    lines.append(
        f'remove [find list={_quote(list_name)} comment~{_quote("^" + COMMENT_PREFIX)}]'
    )
    for address, entry in domains + ip_entries:
        lines.append(
            f"add list={_quote(list_name)} address={address} "
            f"comment={_quote(_comment(entry))}"
        )

    if include_pbr:
        lines.append("")
        lines.append("/ip/firewall/mangle")
        lines.append(
            f'remove [find comment~{_quote("^" + COMMENT_PREFIX)}]'
        )
        lines.append(
            f"add chain=prerouting dst-address-list={_quote(list_name)} "
            f"action=mark-connection new-connection-mark={_quote(connection_mark)} "
            f"passthrough=yes "
            f"comment={_quote(COMMENT_PREFIX + ' mark VPN connection')}"
        )
        lines.append(
            f"add chain=prerouting src-address-list={_quote(local_networks)} "
            f"connection-mark={_quote(connection_mark)} action=mark-routing "
            f"new-routing-mark={_quote(routing_mark)} passthrough=no "
            f"comment={_quote(COMMENT_PREFIX + ' mark VPN routing')}"
        )
        lines.append("")
        lines.append("/routing/table")
        lines.append(
            f":if ([:len [/routing/table/find name={_quote(routing_table)}]] = 0) "
            f"do={{ add name={_quote(routing_table)} fib }}"
        )
        if vpn_gateway:
            lines.append("")
            lines.append("/ip/route")
            lines.append(f'remove [find comment~{_quote("^" + COMMENT_PREFIX)}]')
            lines.append(
                f"add dst-address=0.0.0.0/0 gateway={_quote(vpn_gateway)} "
                f"routing-table={_quote(routing_table)} "
                f"comment={_quote(COMMENT_PREFIX + ' VPN default route')}"
            )

    content = "\n".join(lines).rstrip() + "\n"
    stats = {
        "exported": len(exported),
        "domains": len(domains),
        "ip_entries": len(ip_entries),
        "skipped_wildcards": skipped_wildcards,
        "duplicates": duplicates,
        "include_pbr": include_pbr,
    }
    return content, stats
