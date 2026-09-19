"""TTL deploy client for /app live view.

Fail-closed when APP_DEPLOY_* credentials are missing.
Default lifetime 7 days; hard max 30 days. Rotate-on-regenerate; /app revoke.
Never put secrets in the URL path or query.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TTL_DAYS = 7
MAX_TTL_DAYS = 30

# Local registry of shares (slug → meta) for revoke/rotate when remote delete is best-effort.
_REGISTRY_NAME = "app-live-shares.json"


@dataclass(frozen=True)
class DeployConfig:
    provider: str  # cloudflare | vercel | generic | ""
    token: str
    base_url: str
    put_url_template: str  # e.g. https://api…/objects/{slug} or empty
    delete_url_template: str
    signing_secret: str
    account_id: str
    project: str
    ttl_days: int

    @property
    def configured(self) -> bool:
        if not self.token or not self.base_url:
            return False
        if self.provider in ("", "none", "off"):
            return False
        return True


@dataclass
class DeployResult:
    ok: bool
    url: str | None = None
    slug: str | None = None
    expires_at: datetime | None = None
    error: str | None = None


def load_deploy_config_from_env() -> DeployConfig:
    ttl_raw = (os.getenv("APP_DEPLOY_TTL_DAYS") or str(DEFAULT_TTL_DAYS)).strip()
    try:
        ttl = int(ttl_raw)
    except ValueError:
        ttl = DEFAULT_TTL_DAYS
    ttl = max(1, min(ttl, MAX_TTL_DAYS))
    return DeployConfig(
        provider=(os.getenv("APP_DEPLOY_PROVIDER") or "").strip().lower(),
        token=(os.getenv("APP_DEPLOY_TOKEN") or os.getenv("APP_DEPLOY_API_TOKEN") or "").strip(),
        base_url=(os.getenv("APP_DEPLOY_BASE_URL") or "").strip().rstrip("/"),
        put_url_template=(os.getenv("APP_DEPLOY_PUT_URL") or "").strip(),
        delete_url_template=(os.getenv("APP_DEPLOY_DELETE_URL") or "").strip(),
        signing_secret=(os.getenv("APP_DEPLOY_SIGNING_SECRET") or "").strip(),
        account_id=(os.getenv("APP_DEPLOY_ACCOUNT_ID") or "").strip(),
        project=(os.getenv("APP_DEPLOY_PROJECT") or "").strip(),
        ttl_days=ttl,
    )


def clamp_ttl_days(days: int | None, cfg: DeployConfig | None = None) -> int:
    default = cfg.ttl_days if cfg else DEFAULT_TTL_DAYS
    d = default if days is None else int(days)
    return max(1, min(d, MAX_TTL_DAYS))


def _registry_path() -> Path:
    root = Path(__file__).resolve().parent.parent / "patient-store"
    root.mkdir(parents=True, exist_ok=True)
    return root / _REGISTRY_NAME


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.is_file():
        return {"shares": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"shares": {}}


def _save_registry(reg: dict[str, Any]) -> None:
    path = _registry_path()
    path.write_text(json.dumps(reg, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def new_slug() -> str:
    return secrets.token_urlsafe(12).replace("-", "").replace("_", "")[:16]


def public_url(cfg: DeployConfig, slug: str, expires_at: datetime) -> str:
    """Signed URL without secrets/PHI — slug + exp + sig only."""
    exp = int(expires_at.timestamp())
    base = f"{cfg.base_url.rstrip('/')}/{slug}.html"
    if not cfg.signing_secret:
        return f"{base}?exp={exp}"
    msg = f"{slug}|{exp}".encode("utf-8")
    sig = hmac.new(cfg.signing_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:24]
    return f"{base}?exp={exp}&sig={sig}"


def _http_put(url: str, body: bytes, token: str, content_type: str = "text/html; charset=utf-8") -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _http_delete(url: str, token: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _resolve_put_url(cfg: DeployConfig, slug: str) -> str | None:
    if cfg.put_url_template:
        return cfg.put_url_template.replace("{slug}", slug)
    if cfg.provider == "cloudflare" and cfg.account_id and cfg.project:
        # Cloudflare Pages direct upload placeholder — requires put template in practice
        return None
    if cfg.provider == "vercel" and cfg.project:
        return None
    # generic: base_url used as PUT target root
    if cfg.provider == "generic":
        return f"{cfg.base_url.rstrip('/')}/{slug}.html"
    return None


def _resolve_delete_url(cfg: DeployConfig, slug: str) -> str | None:
    if cfg.delete_url_template:
        return cfg.delete_url_template.replace("{slug}", slug)
    if cfg.put_url_template:
        return cfg.put_url_template.replace("{slug}", slug)
    if cfg.provider == "generic":
        return f"{cfg.base_url.rstrip('/')}/{slug}.html"
    return None


def deploy_live_html(
    html: str,
    *,
    cfg: DeployConfig | None = None,
    ttl_days: int | None = None,
    slug: str | None = None,
    retire_slug: str | None = None,
) -> DeployResult:
    """Upload HTML. Fail-closed if not configured. Optionally retire prior slug."""
    cfg = cfg or load_deploy_config_from_env()
    if not cfg.configured:
        return DeployResult(ok=False, error="not_configured")

    days = clamp_ttl_days(ttl_days, cfg)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=days)
    slug = slug or new_slug()

    if retire_slug and retire_slug != slug:
        revoke_live_slug(retire_slug, cfg=cfg)

    put_url = _resolve_put_url(cfg, slug)
    if not put_url:
        return DeployResult(
            ok=False,
            error="missing_put_url",
            slug=slug,
            expires_at=expires_at,
        )

    # Embed expiry already handled by caller in HTML; upload bytes
    status, body = _http_put(put_url, html.encode("utf-8"), cfg.token)
    if status < 200 or status >= 300:
        logger.warning("app deploy PUT failed status=%s body=%s", status, body[:200])
        return DeployResult(ok=False, error=f"put_failed:{status}", slug=slug, expires_at=expires_at)

    url = public_url(cfg, slug, expires_at)
    reg = _load_registry()
    shares = reg.setdefault("shares", {})
    shares[slug] = {
        "url": url,
        "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provider": cfg.provider,
    }
    _save_registry(reg)
    return DeployResult(ok=True, url=url, slug=slug, expires_at=expires_at)


def revoke_live_slug(slug: str | None, *, cfg: DeployConfig | None = None) -> bool:
    """Best-effort remote delete + local registry clear. True if slug known or deleted."""
    if not slug:
        return False
    cfg = cfg or load_deploy_config_from_env()
    deleted_remote = False
    if cfg.configured:
        del_url = _resolve_delete_url(cfg, slug)
        if del_url:
            status, _body = _http_delete(del_url, cfg.token)
            deleted_remote = 200 <= status < 300 or status == 404
    reg = _load_registry()
    shares = reg.setdefault("shares", {})
    existed = slug in shares
    if existed:
        shares.pop(slug, None)
        _save_registry(reg)
    return deleted_remote or existed


def expires_date_label(expires_at: datetime) -> str:
    """UTC calendar day for caption {date}."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
