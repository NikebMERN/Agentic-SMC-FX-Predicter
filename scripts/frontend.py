#!/usr/bin/env python3
"""Build and dev-serve React frontends (admin + user app)."""
import os
import shutil
import subprocess
import sys

# Project root (parent of scripts/), not the scripts/ folder itself.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_FRONTEND = os.path.join(ROOT, "admin-frontend")
ADMIN_DIST = os.path.join(ROOT, "static", "admin")
SMC_FRONTEND = os.path.join(ROOT, "smc-frontend")
SMC_DIST = os.path.join(ROOT, "static", "app")


def _npm() -> str | None:
    return shutil.which("npm")


def _ensure_npm_deps(cwd: str) -> bool:
    npm = _npm()
    if not npm:
        print("npm not found — install Node.js to run the web frontends.", file=sys.stderr)
        return False
    node_modules = os.path.join(cwd, "node_modules")
    if not os.path.isdir(node_modules):
        subprocess.run([npm, "install"], cwd=cwd, check=True)
    return True


def _vite_dev_process(cwd: str) -> subprocess.Popen | None:
    npm = _npm()
    if not npm or not _ensure_npm_deps(cwd):
        return None
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=cwd,
        **kwargs,
    )


def build_admin_frontend(force: bool = False) -> bool:
    """npm install + vite build. Returns True on success."""
    if not os.path.isdir(ADMIN_FRONTEND):
        print("admin-frontend/ not found", file=sys.stderr)
        return False

    if not force and os.path.isfile(os.path.join(ADMIN_DIST, "index.html")):
        return True

    npm = _npm()
    if not npm:
        print("npm not found — install Node.js to build the React admin panel.", file=sys.stderr)
        return False

    print("Building React admin panel...")
    subprocess.run([npm, "install"], cwd=ADMIN_FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=ADMIN_FRONTEND, check=True)
    print(f"Admin UI built -> {ADMIN_DIST}")
    return os.path.isfile(os.path.join(ADMIN_DIST, "index.html"))


def build_smc_frontend(force: bool = False) -> bool:
    """Build the user-facing smc-frontend into static/app."""
    if not os.path.isdir(SMC_FRONTEND):
        print("smc-frontend/ not found", file=sys.stderr)
        return False

    if not force and os.path.isfile(os.path.join(SMC_DIST, "index.html")):
        return True

    npm = _npm()
    if not npm:
        print("npm not found — install Node.js to build smc-frontend.", file=sys.stderr)
        return False

    print("Building user web app...")
    subprocess.run([npm, "install"], cwd=SMC_FRONTEND, check=True)
    subprocess.run([npm, "run", "build"], cwd=SMC_FRONTEND, check=True)
    print(f"User app built -> {SMC_DIST}")
    return os.path.isfile(os.path.join(SMC_DIST, "index.html"))


def start_admin_dev_server() -> subprocess.Popen | None:
    """Start Vite dev server for hot-reload admin UI (port 5174)."""
    if not os.path.isdir(ADMIN_FRONTEND):
        return None
    return _vite_dev_process(ADMIN_FRONTEND)


def start_smc_dev_server() -> subprocess.Popen | None:
    """Start Vite dev server for the user web app (port 5173)."""
    if not os.path.isdir(SMC_FRONTEND):
        return None
    return _vite_dev_process(SMC_FRONTEND)
