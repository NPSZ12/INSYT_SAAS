#!/usr/bin/env python3
"""Fail-closed clean deployment to the ONE existing INSYT frontend App Service.

Uses GitHub secret AZURE_WEBAPP_PUBLISH_PROFILE_INSYT_APP.
Publishes a built standalone tree with Microsoft's documented Kudu API:
  POST /api/publish?type=zip&clean=true&restart=true
Never modifies Azure resources, app settings, backend, or document storage.
"""

import base64
import http.client
import json
import re
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import zipfile

HOST = "insyt-app-prod-cqfbdbctfcdwb4fp.scm.centralus-01.azurewebsites.net"
SAFE_OLD_ROOT_NAMES = {
    # Only known frontend deployment artifacts should be cleared.
    ".next", "server.js", "node_modules", "public", "package.json",
    "package-lock.json", "next.config.js", "next.config.mjs", "next.config.ts",
    "next-env.d.ts", "tsconfig.json", "tsconfig.tsbuildinfo",
    "eslint.config.js", "eslint.config.mjs", "postcss.config.js",
    "postcss.config.mjs", "README.md", ".gitignore", ".eslintrc.json",
    "src", "app", "components", "hooks", "lib", "styles", "types",
    "utils", "scripts", "middleware.ts", "middleware.js", "assets",
}


def fail(message):
    raise SystemExit(f"STOP: {message}")


def credentials():
    xml = os.environ.get("INSYT_AZURE_PUBLISH_PROFILE", "")
    if not xml:
        fail("Missing configured Azure publish-profile GitHub secret")
    root = ET.fromstring(xml)
    items = root.findall(".//publishProfile")
    # Prefer ZipDeploy site credentials, fall back to MSDeploy site credentials.
    matching = [p for p in items if p.attrib.get("publishMethod") in ("ZipDeploy", "MSDeploy")]
    if not matching:
        fail("No ZipDeploy/MSDeploy credentials in publish profile")
    p = sorted(matching, key=lambda x: x.attrib.get("publishMethod") != "ZipDeploy")[0]
    username, password = p.attrib.get("userName", ""), p.attrib.get("userPWD", "")
    if not username or not password:
        fail("Publish-profile username or password missing")
    return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


def get_vfs(auth, path):
    req = Request(f"https://{HOST}/api/vfs/site/wwwroot/{path}", headers={"Authorization": auth})
    with urlopen(req, timeout=50) as response:
        return response.read()


def build_zip(root, output):
    if not (root / "server.js").is_file():
        fail("Generated standalone server.js missing")
    if not (root / ".next" / "BUILD_ID").is_file():
        fail("Generated standalone BUILD_ID missing")
    if not (root / ".next" / "static").is_dir():
        fail("Generated standalone static chunks missing")
    if (root / ".next" / "standalone").exists():
        fail("Nested duplicate standalone build in deployment package")
    if (root / ".next" / "server" / "route-cache").exists():
        fail("Build/package contains route-cache; refuse stale cached HTML")
    if not (root / ".next" / "server" / "app" / "cyber-utility" / "intake.html").is_file():
        fail("Cyber2 Intake prerendered HTML missing")
    build_id = (root / ".next" / "BUILD_ID").read_text().strip()
    if not build_id or len(build_id) > 128:
        fail("Invalid BUILD_ID")

    source_html = (root / INTAKE_RELATIVE).read_text(encoding="utf-8", errors="replace")
    if not chunk_set(source_html):
        fail("Packaged Cyber2 HTML has no Next.js JS chunk references")
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as z:
        names = set(z.namelist())
        if "server.js" not in names or ".next/BUILD_ID" not in names:
            fail("Incomplete ZIP package")
        if z.read(".next/BUILD_ID").decode().strip() != build_id:
            fail("Build ID mismatch inside ZIP")
        if any("route-cache/" in n or ".next/standalone/" in n for n in names):
            fail("Unexpected nested build/cache found in ZIP")
    print(f"Prepared standalone ZIP, BUILD_ID={build_id}, size={output.stat().st_size} bytes")
    return build_id


# These were observed in the live production root in the 2026-11-21 audit.
# They are NOT required in a standalone deploy package and must be preserved
# outside wwwroot before the first clean release. Never silently remove them.
KNOWN_LEGACY_FILES = {
    ".npmrc", ".ostype", "AGENTS.md", "CLAUDE.md", "_backup.filter",
    "_del_node_modules", "frontend_standalone.zip", "make_deploy_zip.py",
    "node_modules.tar.zst", "oryx-manifest.toml",
}

PUBLIC_URL = "https://www.insyt360.com/cyber-utility/intake"
INTAKE_RELATIVE = ".next/server/app/cyber-utility/intake.html"
CHUNK_PATTERN = re.compile(r"/_next/static/chunks/([^\"'<> ]+?\.js)")


def chunk_set(html):
    return set(CHUNK_PATTERN.findall(html))


def ensure_remote_root_safe(auth):
    try:
        listing = json.loads(get_vfs(auth, "").decode())
    except Exception as exc:
        fail(f"Could not inspect existing production wwwroot; refusing clean deployment: {type(exc).__name__}: {exc}")
    if not isinstance(listing, list):
        fail("Unexpected wwwroot listing format")
    names = {entry.get("name") for entry in listing}
    known_legacy = sorted(str(n) for n in names if n in KNOWN_LEGACY_FILES)
    unknown = sorted(str(n) for n in names if n not in SAFE_OLD_ROOT_NAMES and n not in KNOWN_LEGACY_FILES and not (isinstance(n, str) and n.startswith("server.js.before-") and n.endswith(".bak")))
    # Backups are preserved only outside wwwroot. Avoid discarding these automatically.
    backups = sorted(n for n in names if isinstance(n, str) and n.startswith("server.js.before-") and n.endswith(".bak"))
    if backups:
        fail("Found server.js backup(s) in wwwroot: " + ", ".join(backups) + ". Move these to a safe backup location before clean deployment.")
    if known_legacy:
        fail("Legacy/operational files still in wwwroot: " + ", ".join(known_legacy) + ". Preserve them OUTSIDE wwwroot before first clean deployment. NO deletion performed.")
    if unknown:
        fail("Unexpected production wwwroot entry/entries; refusing to clean: " + ", ".join(unknown))
    if "server.js" not in names or ".next" not in names:
        fail("Current production directory does not match expected Next.js root")
    print("Production wwwroot preflight PASS: only recognized frontend artifacts")


def verify_current_release_before_change(auth):
    """Do not deploy into an unexpectedly altered production app."""
    before = get_vfs(auth, ".next/BUILD_ID").decode().strip()
    if not before:
        fail("Current production build ID empty")
    print(f"Read-only live production preflight: active disk BUILD_ID={before}")


def upload(auth, zpath):
    # Stream data without exposing site credentials in shell command arguments.
    conn = http.client.HTTPSConnection(HOST, timeout=600)
    endpoint = "/api/publish?type=zip&clean=true&restart=true"
    conn.putrequest("POST", endpoint)
    conn.putheader("Authorization", auth)
    conn.putheader("Content-Type", "application/zip")
    conn.putheader("Content-Length", str(zpath.stat().st_size))
    conn.endheaders()
    with zpath.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            conn.send(chunk)
    response = conn.getresponse()
    code = response.status
    detail = response.read(1500).decode("utf-8", "replace")
    location = response.getheader("Location")
    conn.close()
    if code not in (200, 201, 202, 204):
        fail(f"Clean publish failed HTTP {code}: {detail[:600]}")
    print(f"Clean publish HTTP {code}; target EXISTING insyt-app-prod; restart=true")
    if code == 202 and location:
        # Do not claim success from an accepted-but-still-running deployment.
        parsed = urlparse(location)
        if parsed.hostname != HOST or parsed.scheme != "https":
            fail("Deployment accepted asynchronously but returned an unexpected status URL")
        for _ in range(30):
            time.sleep(10)
            r = Request(location, headers={"Authorization": auth})
            with urlopen(r, timeout=45) as answer:
                status = answer.status
                payload = answer.read(3000)
            if status == 202:
                continue
            if status not in (200, 201, 204):
                fail(f"Asynchronous clean deployment returned HTTP {status}")
            break
        else:
            fail("Deployment still pending after 5 minutes; inspect Azure deployment logs")


def verify(auth, expected_build_id):
    # Existence + exact build match, not just GitHub Actions 'green'.
    for attempt in range(12):
        try:
            actual = get_vfs(auth, ".next/BUILD_ID").decode().strip()
            if actual == expected_build_id:
                break
        except Exception:
            pass
        time.sleep(10)
    else:
        fail("Azure production BUILD_ID does not match the deployed package")
    body = get_vfs(auth, ".next/server/app/cyber-utility/intake.html").decode("utf-8", "replace")
    if "_next/static" not in body:
        fail("Deployed Cyber2 Intake HTML lacks Next.js static assets")
    expected_chunks = chunk_set(body)
    if not expected_chunks:
        fail("Deployed Cyber2 Intake HTML contains no identifiable Next.js chunks")
    print("PASS: Azure BUILD_ID and compiled Cyber2 HTML verified")
    return expected_chunks


def verify_live(expected_chunks):
    """Detect the exact stale HTML incident that caused the Nov 2026 outage.

    A CDN/browser cache is not sufficient: fetch the origin-bound public page
    with no-cache request headers, and confirm it references the deployed bundle.
    """
    last_error = "no response"
    for attempt in range(12):
        try:
            req = Request(PUBLIC_URL, headers={
                "Cache-Control": "no-cache", "Pragma": "no-cache",
                "User-Agent": "INSYT-frontend-release-verifier/1.0",
            })
            with urlopen(req, timeout=30) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP {response.status}")
                live_html = response.read(5_000_000).decode("utf-8", "replace")
            live_chunks = chunk_set(live_html)
            if expected_chunks.issubset(live_chunks):
                print("PASS: Live public Cyber2 HTML references the deployed JS chunks")
                return
            last_error = (f"Live/deployed chunk mismatch; expected={sorted(expected_chunks)[:10]}, "
                          f"live={sorted(live_chunks)[:10]}")
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        print(f"Live verification pending ({attempt+1}/12): {last_error}")
        time.sleep(10)
    fail("PRODUCTION LIVE VERIFY FAILED after deployment; inspect and roll back from preserved release. " + last_error)


def main():
    if len(sys.argv) != 2:
        fail("Expected exactly one release package directory argument")
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        fail("Missing release package directory")
    zpath = Path("frontend_clean_release.zip").resolve()
    build_id = build_zip(root, zpath)
    auth = credentials()
    ensure_remote_root_safe(auth)  # No changes if the root is unexpected.
    verify_current_release_before_change(auth)
    upload(auth, zpath)
    expected_chunks = verify(auth, build_id)
    verify_live(expected_chunks)


if __name__ == "__main__":
    main()
