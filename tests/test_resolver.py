import asyncio
import socket

import rscforge.resolver as resolver


def _reset_cache() -> None:
    resolver._cache.clear()


def _infos(*addresses: str) -> list[tuple]:
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))
        for address in addresses
    ]


def test_resolve_domains_deduplicates_requests_and_addresses(monkeypatch) -> None:
    _reset_cache()
    calls: list[str] = []

    def fake(host, port, family=0, type=0):
        calls.append(host)
        return _infos("1.2.3.4", "1.2.3.4", "5.6.7.8")

    monkeypatch.setattr(socket, "getaddrinfo", fake)

    result = asyncio.run(
        resolver.resolve_domains(["b.example", "a.example", "a.example"])
    )

    assert calls == ["a.example", "b.example"]
    assert result == {
        "a.example": ["1.2.3.4", "5.6.7.8"],
        "b.example": ["1.2.3.4", "5.6.7.8"],
    }


def test_resolve_domain_uses_cache(monkeypatch) -> None:
    _reset_cache()
    calls: list[str] = []

    def fake(host, port, family=0, type=0):
        calls.append(host)
        return _infos("1.2.3.4")

    monkeypatch.setattr(socket, "getaddrinfo", fake)

    assert asyncio.run(resolver.resolve_domain("cached.example")) == ("1.2.3.4",)
    assert asyncio.run(resolver.resolve_domain("cached.example")) == ("1.2.3.4",)
    assert calls == ["cached.example"]


def test_temporary_failure_keeps_stale_cache(monkeypatch) -> None:
    _reset_cache()
    resolver._cache["stale.example"] = (0.0, ("9.9.9.9",))

    def failing(host, port, family=0, type=0):
        raise socket.gaierror(socket.EAI_AGAIN, "temporary failure")

    monkeypatch.setattr(socket, "getaddrinfo", failing)

    assert asyncio.run(resolver.resolve_domain("stale.example")) == ("9.9.9.9",)


def test_unknown_domain_is_negative_cached(monkeypatch) -> None:
    _reset_cache()

    def missing(host, port, family=0, type=0):
        raise socket.gaierror(socket.EAI_NONAME, "no such host")

    monkeypatch.setattr(socket, "getaddrinfo", missing)

    assert asyncio.run(resolver.resolve_domain("missing.example")) == ()
