from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from .. import repositories as repo
from ..config import settings
from ..schemas import SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _public(values: dict[str, str]) -> dict:
    return {
        "list_name": values.get("list_name", "vpn-filter"),
        "include_pbr": values.get("include_pbr") == "true",
        "vpn_gateway": values.get("vpn_gateway", ""),
        "routing_table": values.get("routing_table", "new-con"),
        "connection_mark": values.get("connection_mark", "vpn-filter-con"),
        "routing_mark": values.get("routing_mark", "new-con"),
        "local_networks_list": values.get("local_networks_list", "local-networks"),
        "wildcard_policy": values.get("wildcard_policy", "skip"),
    }


def _payload() -> dict:
    return {
        "values": _public(repo.get_settings()),
        "readonly": {
            "username": settings.username,
            "auth_enabled": bool(settings.password),
            "export_token_enabled": bool(settings.export_token),
            "version": __version__,
        },
    }


@router.get("")
def get_settings() -> dict:
    return _payload()


@router.patch("")
def update_settings(payload: SettingsUpdate) -> dict:
    stored: dict[str, str] = {}
    for key, value in payload.model_dump(exclude_none=True).items():
        if isinstance(value, bool):
            stored[key] = "true" if value else "false"
        else:
            stored[key] = str(value).strip()
    repo.set_settings(stored)
    return _payload()
