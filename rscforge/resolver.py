from __future__ import annotations

import asyncio
import logging
import socket
import time
from collections.abc import Iterable

from .config import settings

logger = logging.getLogger(__name__)


class TemporaryDnsError(RuntimeError):
    """Resolver is temporarily unavailable (not an authoritative NXDOMAIN)."""


# domain -> (expires_at_monotonic, ipv4 addresses)
_cache: dict[str, tuple[float, tuple[str, ...]]] = {}


def _lookup(domain: str) -> tuple[str, ...]:
    try:
        infos = socket.getaddrinfo(
            domain, None, family=socket.AF_INET, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        if exc.errno in {socket.EAI_AGAIN, socket.EAI_FAIL}:
            raise TemporaryDnsError(str(exc)) from exc
        return ()
    except OSError as exc:
        raise TemporaryDnsError(str(exc)) from exc

    addresses: list[str] = []
    seen: set[str] = set()
    for info in infos:
        address = info[4][0]
        if address not in seen:
            seen.add(address)
            addresses.append(address)
    return tuple(addresses)


async def resolve_domain(
    domain: str, semaphore: asyncio.Semaphore | None = None
) -> tuple[str, ...]:
    now = time.monotonic()
    cached = _cache.get(domain)
    if cached is not None and cached[0] > now:
        return cached[1]

    limit = semaphore or asyncio.Semaphore(settings.dns_concurrency)
    try:
        async with limit:
            addresses = await asyncio.wait_for(
                asyncio.to_thread(_lookup, domain), timeout=settings.dns_timeout
            )
    except (TemporaryDnsError, asyncio.TimeoutError) as exc:
        reason = str(exc) or "таймаут"
        if cached is not None:
            logger.warning(
                "DNS %s: %s — использую устаревший кэш (%s адресов)",
                domain,
                reason,
                len(cached[1]),
            )
            return cached[1]
        logger.warning("DNS %s: %s — домен пропущен", domain, reason)
        addresses = ()

    _cache[domain] = (time.monotonic() + settings.dns_cache_ttl, addresses)
    return addresses


async def resolve_domains(domains: Iterable[str]) -> dict[str, list[str]]:
    """Resolve unique domains to IPv4 addresses in parallel."""
    unique = sorted({domain for domain in domains if domain})
    if not unique:
        return {}
    semaphore = asyncio.Semaphore(settings.dns_concurrency)
    results = await asyncio.gather(
        *(resolve_domain(domain, semaphore) for domain in unique)
    )
    return {
        domain: list(addresses)
        for domain, addresses in zip(unique, results)
    }
