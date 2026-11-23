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


def _entry_label(entry: dict) -> str:
    label = (entry.get("comment") or "").strip()
    if not label:
        source = (entry.get("source_name") or "").strip()
        label = f"src={source}" if source else "manual"
    return label


def _domain_label(entry: dict, domain: str) -> str:
    label = (entry.get("comment") or "").strip()
    if label and label != domain:
        return f"{domain} ({label})"
    return domain


def _comment(labels: list[str]) -> str:
    unique = list(dict.fromkeys(label for label in labels if label))
    return f"{COMMENT_PREFIX}{_clean_comment(', '.join(unique))}"


def _ip_sort_key(entry: dict) -> tuple:
    try:
        network = ipaddress.ip_network(entry["normalized"], strict=False)
        return (network.version, int(network.network_address), network.prefixlen)
    except ValueError:
        return (9, 0, 0)


def domain_targets(entries: list[dict], settings: dict[str, str]) -> set[str]:
    """Return domain names that need to be resolved for this export."""
    wildcard_policy = settings.get("wildcard_policy") or "base-domain"
    targets: set[str] = set()
    for entry in entries:
        if entry.get("kind") != "domain":
            continue
        normalized = entry.get("normalized") or ""
        if normalized.startswith("*."):
            if wildcard_policy != "base-domain":
                continue
            normalized = normalized[2:]
        if normalized:
            targets.add(normalized)
    return targets


def generate_rsc(
    entries: list[dict],
    settings: dict[str, str],
    resolved: dict[str, list[str]],
) -> tuple[str, dict]:
    list_name = (settings.get("list_name") or "vpn-filter").strip()
    include_pbr = _as_bool(settings.get("include_pbr"))
    wildcard_policy = settings.get("wildcard_policy") or "base-domain"

    vpn_gateway = (settings.get("vpn_gateway") or "").strip()
    routing_mark = (settings.get("routing_mark") or list_name).strip()
    routing_table = (settings.get("routing_table") or routing_mark).strip()
    connection_mark = (settings.get("connection_mark") or f"{list_name}-con").strip()
    local_networks = (settings.get("local_networks_list") or "local-networks").strip()

    # address -> comment labels (domains and/or manual labels)
    addresses: dict[str, list[str]] = {}
    seen: set[str] = set()
    skipped_wildcards = 0
    duplicates = 0
    domains = 0
    resolved_domains = 0
    unresolved_domains = 0
    resolved_ips = 0
    ip_entries = 0

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

        if entry["kind"] == "domain":
            domains += 1
            ips = resolved.get(normalized) or []
            if not ips:
                unresolved_domains += 1
                continue
            resolved_domains += 1
            resolved_ips += len(ips)
            label = _domain_label(entry, normalized)
            for address in ips:
                addresses.setdefault(address, []).append(label)
        else:
            ip_entries += 1
            addresses.setdefault(normalized, []).append(_entry_label(entry))

    ordered = sorted(
        addresses.items(),
        key=lambda item: _ip_sort_key({"normalized": item[0]}),
    )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = [
        "# RscForge export",
        f"# generated: {now}",
        f"# list: {list_name}",
        f"# entries: {len(ordered)} "
        f"(resolved domains: {resolved_domains}, "
        f"ip/cidr: {ip_entries}, "
        f"unresolved domains: {unresolved_domains})",
        f"# resolved IPs from domains: {resolved_ips}",
    ]
    if unresolved_domains:
        lines.append(f"# unresolved domains: {unresolved_domains}")
    if skipped_wildcards:
        lines.append(f"# skipped wildcard domains: {skipped_wildcards}")
    if include_pbr and not vpn_gateway:
        lines.append("# WARNING: PBR enabled, but vpn_gateway is empty — route was not generated")
    lines.append("")

    lines.append("/ip/firewall/address-list")
    lines.append(
        f'remove [find list={_quote(list_name)} comment~{_quote("^" + COMMENT_PREFIX)}]'
    )
    for address, labels in ordered:
        lines.append(
            f"add list={_quote(list_name)} address={address} "
            f"comment={_quote(_comment(labels))}"
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
        "exported": len(ordered),
        "domains": domains,
        "resolved_domains": resolved_domains,
        "unresolved_domains": unresolved_domains,
        "resolved_ips": resolved_ips,
        "ip_entries": ip_entries,
        "skipped_wildcards": skipped_wildcards,
        "duplicates": duplicates,
        "include_pbr": include_pbr,
    }
    return content, stats
