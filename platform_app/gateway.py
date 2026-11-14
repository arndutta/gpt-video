"""Safe alias availability checks using current memory-only gateway configuration."""

import asyncio
import hashlib
import json
from datetime import datetime, timezone

import httpx

from platform_app.config import tls_context
from platform_app.llm.safety import redact

ROLES = ("router", "narrator", "analyst", "strategist")
VERIFY_TIMEOUT_SECONDS = 10


class GatewayError(RuntimeError):
    def __init__(self, code, detail, *, available_models=None, missing_models=None):
        self.code, self.detail = code, detail
        self.available_models, self.missing_models = available_models or [], missing_models or []
        super().__init__(detail)


def signature(settings):
    # This credential-derived fingerprint is memory-only and never logged/persisted.
    values = [settings.gateway_base_url, settings.api_key.get_secret_value() if settings.api_key else None,
              settings.verify_tls, *[getattr(settings, "model_" + role) for role in ROLES]]
    return hashlib.sha256(json.dumps(values).encode()).digest()


async def verify_gateway(settings, transport=None):
    missing_roles = [r for r in ROLES if not getattr(settings, "model_" + r)]
    if not settings.gateway_base_url or not settings.api_key or missing_roles:
        raise GatewayError("unconfigured", "Configure the gateway URL, API key and all four model aliases before verification.")
    try:
        # HTTPX bounds individual operations; a slow stream also needs a total deadline.
        async with asyncio.timeout(VERIFY_TIMEOUT_SECONDS), httpx.AsyncClient(
                verify=tls_context(settings), timeout=VERIFY_TIMEOUT_SECONDS, transport=transport,
                follow_redirects=False) as client:
            async with client.stream("GET", settings.gateway_base_url + "/models", headers={
                    "Authorization": "Bearer " + settings.api_key.get_secret_value()}) as response:
                response.raise_for_status()
                parts, size = [], 0
                async for part in response.aiter_bytes():
                    size += len(part)
                    if size > 2_000_000:
                        raise ValueError("Model list exceeds its bound")
                    parts.append(part)
        payload = json.loads(b"".join(parts))
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) > 4096:
            raise ValueError("Invalid model list")
        available = set()
        for row in rows:
            model = row.get("id") if isinstance(row, dict) else None
            if not isinstance(model, str) or not 1 <= len(model) <= 200:
                raise ValueError("Invalid model identifier")
            available.add(model)
    except (httpx.HTTPError, ValueError, OSError, TimeoutError):
        raise GatewayError("unavailable", "Gateway model verification failed. Check access, credentials, model-list support and corporate CA settings.") from None
    missing = sorted({getattr(settings, "model_" + role) for role in ROLES} - available)
    if missing:
        clean = lambda values: redact(values, [settings.api_key.get_secret_value()])
        raise GatewayError("missing_models", "Some configured aliases are absent from the gateway model list.",
                           available_models=clean(sorted(available)), missing_models=clean(missing))
    return {"status": "verified", "verified": True, "detail": "All four configured aliases are advertised by the gateway.",
            "structured_output_verified": False, "checked_at": datetime.now(timezone.utc).isoformat()}


class GatewayReadiness:
    def __init__(self, settings_provider, store, transport=None):
        self.settings_provider, self.store, self.transport = settings_provider, store, transport
        self._signature, self._result, self._lock = None, None, asyncio.Lock()

    def current(self):
        settings = self.settings_provider()
        roles = {r: bool(getattr(settings, "model_" + r)) for r in ROLES}
        base = {"configured": bool(settings.gateway_url), "key_configured": bool(settings.api_key),
                "startup_mode": settings.startup_mode,
                "configured_roles": roles, "missing_roles": [r for r, configured in roles.items() if not configured],
                "verified": False, "structured_output_verified": False, "checked_at": None,
                "status": "configured" if settings.gateway_url and settings.api_key and all(roles.values()) else "unconfigured",
                "detail": "Verify the current gateway configuration." if settings.gateway_url else "Enter gateway settings to verify model availability."}
        if self._signature == signature(settings) and self._result:
            base.update(self._result)
        return base

    async def check(self, *, actor="human"):
        async with self._lock:
            settings = self.settings_provider().model_copy(deep=True)
            expected = signature(settings)
            try:
                result = await verify_gateway(settings, self.transport)
            except GatewayError as error:
                result = {"status": error.code, "verified": False, "detail": error.detail,
                          "checked_at": datetime.now(timezone.utc).isoformat(),
                          "available_models": error.available_models, "missing_models": error.missing_models}
            if expected != signature(self.settings_provider()):
                return {**self.current(), "status": "configuration_changed", "verified": False,
                        "detail": "Settings changed during verification. Verify the current configuration again."}
            self._signature, self._result = expected, result
            self.store.audit("gateway_verified" if result["verified"] else "gateway_verification_failed",
                             {"status": result["status"], "roles": list(ROLES)}, actor=actor)
            return self.current()
