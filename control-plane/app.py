import json
import os
import re
import threading
import errno
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)

PROXY_PROPERTIES_FILE = Path(os.getenv("PROXY_PROPERTIES_FILE", "/config/camellia-redis-proxy.properties"))
TENANTS_FILE = Path(os.getenv("TENANTS_FILE", "/data/tenants.json"))
AUDIT_FILE = Path(os.getenv("AUDIT_FILE", "/data/audit.log"))
APP_PORT = int(os.getenv("APP_PORT", "8080"))

MANAGED_START = "# -- managed-tenants:start --"
MANAGED_END = "# -- managed-tenants:end --"

TENANT_ID_RE = re.compile(r"^[a-z0-9_]+$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9_]+$")
BGROUP_RE = re.compile(r"^[A-Za-z0-9_]+$")

BACKEND_ROUTE = {
    "pool_a": "redis://@redis-pool-a:6379",
    "pool_b": "redis://@redis-pool-b:6379",
    "pool_c": "redis://@redis-pool-c:6379",
}

TIER_BACKEND = {
    "shared-small": "pool_a",
    "shared-medium": "pool_b",
    "dedicated": "pool_c",
}

DEFAULT_TENANTS = {
    "tenant_a": {
        "password": "tenantApwd",
        "bid": 1,
        "bgroup": "default",
        "tier": "shared-small",
        "backend": "pool_a",
    },
    "tenant_b": {
        "password": "tenantBpwd",
        "bid": 2,
        "bgroup": "default",
        "tier": "shared-medium",
        "backend": "pool_b",
    },
}

lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, content: str) -> None:
    ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError as e:
        if e.errno != errno.EBUSY:
            raise
        with path.open("w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if tmp.exists():
            tmp.unlink()


def load_tenants() -> dict:
    if not TENANTS_FILE.exists():
        save_tenants(DEFAULT_TENANTS)
    raw = TENANTS_FILE.read_text(encoding="utf-8")
    return json.loads(raw)


def save_tenants(tenants: dict) -> None:
    atomic_write(TENANTS_FILE, json.dumps(tenants, indent=2, sort_keys=True) + "\n")


def tenant_route_line(tenant: dict) -> str:
    route = BACKEND_ROUTE[tenant["backend"]]
    return f"{tenant['password']}.password.{tenant['bid']}.{tenant['bgroup']}.route.conf={route}"


def update_proxy_properties(tenants: dict) -> None:
    if not PROXY_PROPERTIES_FILE.exists():
        raise RuntimeError(f"properties file not found: {PROXY_PROPERTIES_FILE}")

    lines = PROXY_PROPERTIES_FILE.read_text(encoding="utf-8").splitlines()
    managed_lines = [tenant_route_line(tenants[k]) for k in sorted(tenants.keys())]

    try:
        start_idx = lines.index(MANAGED_START)
        end_idx = lines.index(MANAGED_END)
        if end_idx <= start_idx:
            raise ValueError("invalid managed block markers")
        new_lines = lines[: start_idx + 1] + managed_lines + lines[end_idx:]
    except ValueError:
        new_lines = lines + ["", MANAGED_START] + managed_lines + [MANAGED_END]

    atomic_write(PROXY_PROPERTIES_FILE, "\n".join(new_lines) + "\n")


def log_audit(action: str, payload: dict) -> None:
    ensure_parent(AUDIT_FILE)
    entry = {
        "ts": now_iso(),
        "action": action,
        "payload": payload,
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")


def validate_payload(tenant_id: str, password: str, bid: int, bgroup: str, backend: str) -> None:
    if not TENANT_ID_RE.match(tenant_id):
        raise ValueError("tenant_id must match [a-z0-9_]+")
    if not PASSWORD_RE.match(password):
        raise ValueError("password must match [A-Za-z0-9_]+ for Camellia route key")
    if bid <= 0:
        raise ValueError("bid must be > 0")
    if not BGROUP_RE.match(bgroup):
        raise ValueError("bgroup must match [A-Za-z0-9_]+")
    if backend not in BACKEND_ROUTE:
        raise ValueError(f"backend must be one of {sorted(BACKEND_ROUTE.keys())}")


def resolve_backend(payload: dict, current_tier: str = "shared-small") -> tuple[str, str]:
    tier = payload.get("tier", current_tier)
    if tier not in TIER_BACKEND:
        raise ValueError(f"tier must be one of {sorted(TIER_BACKEND.keys())}")
    backend = payload.get("backend", TIER_BACKEND[tier])
    if backend not in BACKEND_ROUTE:
        raise ValueError(f"backend must be one of {sorted(BACKEND_ROUTE.keys())}")
    return tier, backend


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "time": now_iso()})


@app.get("/tenants")
def list_tenants():
    with lock:
        tenants = load_tenants()
    return jsonify({"tenants": tenants})


@app.post("/tenants")
def create_tenant():
    payload = request.get_json(force=True, silent=False)
    tenant_id = payload.get("tenant_id")
    password = payload.get("password")
    bid = int(payload.get("bid", 0))
    bgroup = payload.get("bgroup", "default")

    tier, backend = resolve_backend(payload)
    validate_payload(tenant_id, password, bid, bgroup, backend)

    with lock:
        tenants = load_tenants()
        if tenant_id in tenants:
            return jsonify({"error": "tenant already exists"}), 409

        tenants[tenant_id] = {
            "password": password,
            "bid": bid,
            "bgroup": bgroup,
            "tier": tier,
            "backend": backend,
        }
        save_tenants(tenants)
        update_proxy_properties(tenants)
        log_audit("create_tenant", {"tenant_id": tenant_id, **tenants[tenant_id]})

    return jsonify({"status": "created", "tenant": tenants[tenant_id]})


@app.post("/tenants/<tenant_id>/migrate")
def migrate_tenant(tenant_id: str):
    payload = request.get_json(force=True, silent=False)
    with lock:
        tenants = load_tenants()
        tenant = tenants.get(tenant_id)
        if not tenant:
            return jsonify({"error": "tenant not found"}), 404

        tier, backend = resolve_backend(payload, current_tier=tenant.get("tier", "shared-small"))
        old_backend = tenant["backend"]
        tenant["tier"] = tier
        tenant["backend"] = backend
        tenants[tenant_id] = tenant

        save_tenants(tenants)
        update_proxy_properties(tenants)
        log_audit(
            "migrate_tenant",
            {
                "tenant_id": tenant_id,
                "from_backend": old_backend,
                "to_backend": backend,
                "tier": tier,
            },
        )

    return jsonify(
        {
            "status": "migrated",
            "tenant_id": tenant_id,
            "from_backend": old_backend,
            "to_backend": backend,
            "reload_hint": "Camellia reloads dynamic config every ~2s in this lab",
        }
    )


@app.delete("/tenants/<tenant_id>")
def delete_tenant(tenant_id: str):
    with lock:
        tenants = load_tenants()
        if tenant_id not in tenants:
            return jsonify({"error": "tenant not found"}), 404
        deleted = tenants.pop(tenant_id)
        save_tenants(tenants)
        update_proxy_properties(tenants)
        log_audit("delete_tenant", {"tenant_id": tenant_id, **deleted})
    return jsonify({"status": "deleted", "tenant_id": tenant_id})


@app.get("/audit")
def get_audit():
    limit = int(request.args.get("limit", 100))
    if limit <= 0:
        limit = 100
    if not AUDIT_FILE.exists():
        return jsonify({"items": []})

    lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    tail = lines[-limit:]
    items = [json.loads(line) for line in tail if line.strip()]
    return jsonify({"items": items})


def bootstrap():
    with lock:
        tenants = load_tenants()
        update_proxy_properties(tenants)
        log_audit("bootstrap_sync", {"tenant_count": len(tenants)})


if __name__ == "__main__":
    bootstrap()
    app.run(host="0.0.0.0", port=APP_PORT)
