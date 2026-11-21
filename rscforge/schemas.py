from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

ROUTEROS_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
GATEWAY_RE = re.compile(r"^[A-Za-z0-9_.:%@/-]{1,128}$")


def _validate_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL должен начинаться с http:// или https://")
    return value


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=1, max_length=2000)
    refresh_interval_minutes: int = Field(60, ge=5, le=10080)
    enabled: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_url(value)


class SourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    url: str | None = Field(None, min_length=1, max_length=2000)
    refresh_interval_minutes: int | None = Field(None, ge=5, le=10080)
    enabled: bool | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _validate_url(value) if value is not None else None


class EntryCreate(BaseModel):
    value: str = Field(..., min_length=1, max_length=20000)
    comment: str | None = Field(None, max_length=200)
    enabled: bool = True


class EntryUpdate(BaseModel):
    value: str | None = Field(None, min_length=1, max_length=2000)
    comment: str | None = Field(None, max_length=200)
    enabled: bool | None = None


class BulkEntries(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=10000)
    action: Literal["enable", "disable", "delete"]


class SettingsUpdate(BaseModel):
    list_name: str | None = None
    include_pbr: bool | None = None
    vpn_gateway: str | None = Field(None, max_length=128)
    routing_table: str | None = None
    connection_mark: str | None = None
    routing_mark: str | None = None
    local_networks_list: str | None = None
    wildcard_policy: Literal["skip", "base-domain"] | None = None

    @field_validator(
        "list_name",
        "routing_table",
        "connection_mark",
        "routing_mark",
        "local_networks_list",
    )
    @classmethod
    def validate_routeros_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not ROUTEROS_NAME_RE.match(value):
            raise ValueError(
                "Имя должно содержать только A-Z, a-z, 0-9, '_', '.', '-' (до 64 символов)"
            )
        return value

    @field_validator("vpn_gateway")
    @classmethod
    def validate_gateway(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if value and not GATEWAY_RE.match(value):
            raise ValueError("Некорректный адрес/интерфейс VPN-шлюза")
        return value
