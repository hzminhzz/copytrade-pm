"""Bounded public Hyperliquid REST access and complete DEX census validation."""

from hashlib import sha256
import json
import re
from typing import Any
from urllib.request import Request, urlopen

INFO_URL = "https://api.hyperliquid.xyz/info"
INFO_ENDPOINT = INFO_URL
MAX_BODY = 3_000_000
# These are explicit provider modes, not a claim that balances are additive.
PUBLIC_ACCOUNT_MODES = frozenset(
    {"default", "disabled", "dexAbstraction", "unifiedAccount", "portfolioMargin"}
)


def guarded_info(request: dict[str, Any]) -> tuple[Any, bytes, str]:
    body = (
        json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    )
    url = Request(
        INFO_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "OpenAI File Downloader, XaiImageApiFetch/1.0",
        },
    )
    with urlopen(url, timeout=18) as response:
        raw = response.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise ValueError("E4_PROVIDER_RESPONSE_TOO_LARGE")
    parsed = json.loads(raw)
    if request.get("type") == "userAbstraction":
        if type(parsed) is not str or parsed not in PUBLIC_ACCOUNT_MODES:
            raise ValueError("E4_UNKNOWN_PUBLIC_ACCOUNT_ABSTRACTION")
    elif parsed is not None and not isinstance(parsed, (list, dict)):
        raise ValueError("E4_INVALID_PROVIDER_JSON")
    return parsed, raw, sha256(raw).hexdigest()


def dex_universe(body: object) -> set[str]:
    """Official perpDexs: null is default; named entries are HIP-3 DEXes."""
    if not isinstance(body, list) or not body or body[0] is not None:
        raise ValueError("E4_INVALID_DEX_CATALOG")
    names = {"default"}
    for item in body[1:]:
        if not isinstance(item, dict):
            raise ValueError("E4_INVALID_DEX_CATALOG")
        name = item.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError("E4_INVALID_DEX_NAME")
        if name in names:
            raise ValueError("E4_DUPLICATE_DEX")
        names.add(name)
    return names
