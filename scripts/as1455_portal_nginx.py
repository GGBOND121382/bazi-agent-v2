#!/usr/bin/env python3
"""Locate and patch the live Nginx server that serves the shared portal.

The resolver does not trust file names or static heuristics alone. It reads the
configuration files reported by ``nginx -T`` and uses a temporary exact-match
probe location to identify the server block that actually handles requests to
127.0.0.1:<port>. Every probe edit is restored before the command returns.
"""
from __future__ import annotations

import argparse
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

BEGIN = "    # BEGIN AS1455 DASHBOARD"
END = "    # END AS1455 DASHBOARD"
CONFIG_MARKER = re.compile(r"(?m)^# configuration file (/.+?):\s*$")


@dataclass(frozen=True)
class ServerBlock:
    index: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Candidate:
    path: Path
    block_index: int


def mask_comments(text: str) -> str:
    return re.sub(r"(?m)#.*$", lambda match: " " * len(match.group(0)), text)


def iter_server_blocks(text: str) -> Iterable[ServerBlock]:
    masked = mask_comments(text)
    block_index = 0
    for match in re.finditer(r"\bserver\s*\{", masked):
        brace_start = masked.find("{", match.start(), match.end())
        depth = 0
        for index in range(brace_start, len(masked)):
            if masked[index] == "{":
                depth += 1
            elif masked[index] == "}":
                depth -= 1
                if depth == 0:
                    yield ServerBlock(
                        block_index,
                        match.start(),
                        index + 1,
                        text[match.start() : index + 1],
                    )
                    block_index += 1
                    break
        else:
            raise ValueError("Nginx server block has unbalanced braces")


def listens_on_port(block: str, port: int) -> bool:
    return bool(
        re.search(
            rf"(?m)^\s*listen\s+(?:(?:\[[^]]+\]|[^\s;:]+):)?{port}(?:\s|;)",
            block,
        )
    )


def portal_hint_score(block: str, web_root: str) -> int:
    root_match = re.search(r"(?m)^\s*root\s+([^;]+);", block)
    root = root_match.group(1).strip().strip("\"'").rstrip("/") if root_match else ""
    expected_root = web_root.rstrip("/")
    score = 0
    if root == expected_root:
        score += 100
    if re.search(r"location\s*=\s*/\s*\{", block) and re.search(
        r"try_files\s+/index\.html", block
    ):
        score += 30
    if re.search(r"(?m)^\s*listen\s+[^;]*\bdefault_server\b[^;]*;", block):
        score += 10
    return score


def nginx_dump() -> str:
    result = subprocess.run(["nginx", "-T"], check=False, capture_output=True, text=True)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        raise ValueError(output.strip() or f"nginx -T exited with {result.returncode}")
    return output


def loaded_config_paths(dump: str) -> list[Path]:
    result: list[Path] = []
    for marker in CONFIG_MARKER.finditer(dump):
        path = Path(marker.group(1)).resolve()
        if path.is_file() and path not in result:
            result.append(path)
    if not result:
        raise ValueError("nginx -T did not expose any loaded configuration files")
    return result


def candidate_blocks(paths: Iterable[Path], port: int, web_root: str) -> list[Candidate]:
    ranked: list[tuple[int, Candidate]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for block in iter_server_blocks(text):
            if listens_on_port(block.text, port):
                ranked.append(
                    (portal_hint_score(block.text, web_root), Candidate(path, block.index))
                )
    if not ranked:
        raise ValueError(f"no loaded Nginx server listens on port {port}")
    ranked.sort(key=lambda item: (-item[0], str(item[1].path), item[1].block_index))
    return [candidate for _, candidate in ranked]


def reload_nginx() -> None:
    commands = (["systemctl", "reload", "nginx.service"], ["nginx", "-s", "reload"])
    details: list[str] = []
    for command in commands:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0:
            return
        details.append((result.stderr or result.stdout or " ".join(command)).strip())
    raise ValueError("could not reload Nginx: " + " | ".join(details))


def check_nginx() -> None:
    result = subprocess.run(["nginx", "-t"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout).strip() or "nginx -t failed")


def request_probe(port: int, path: str, expected: str) -> bool:
    url = f"http://127.0.0.1:{port}{path}"
    request = urllib.request.Request(
        url,
        headers={"Host": "127.0.0.1", "Connection": "close"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(15):
        try:
            with opener.open(request, timeout=1) as response:
                if (
                    response.status == 204
                    and response.headers.get("X-AS1455-Probe") == expected
                ):
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code == 204 and exc.headers.get("X-AS1455-Probe") == expected:
                return True
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(0.1)
    return False


def insert_into_block(text: str, block_index: int, payload: str) -> str:
    blocks = list(iter_server_blocks(text))
    if block_index < 0 or block_index >= len(blocks):
        raise ValueError(f"server block index {block_index} is no longer valid")
    target = blocks[block_index]
    insert_at = target.end - 1
    return text[:insert_at].rstrip() + "\n\n" + payload.rstrip() + "\n" + text[insert_at:]


def probe_payload(token: str, candidate_id: str) -> tuple[str, str]:
    path = f"/__as1455_probe_{token}"
    payload = f"""    # BEGIN AS1455 PROBE {token}
    location = {path} {{
        add_header X-AS1455-Probe \"{candidate_id}\" always;
        return 204;
    }}
    # END AS1455 PROBE {token}"""
    return path, payload


def discover_active_candidate(candidates: list[Candidate], port: int) -> Candidate:
    originals: dict[Path, str] = {}
    for candidate in candidates:
        if candidate.path not in originals:
            originals[candidate.path] = candidate.path.read_text(encoding="utf-8")

    try:
        for ordinal, candidate in enumerate(candidates):
            token = secrets.token_hex(8)
            candidate_id = f"{ordinal}-{token}"
            probe_path, payload = probe_payload(token, candidate_id)
            original = originals[candidate.path]
            candidate.path.write_text(
                insert_into_block(original, candidate.block_index, payload),
                encoding="utf-8",
            )
            try:
                try:
                    check_nginx()
                except ValueError:
                    continue
                reload_nginx()
                if request_probe(port, probe_path, candidate_id):
                    return candidate
            finally:
                candidate.path.write_text(original, encoding="utf-8")
                check_nginx()
                reload_nginx()
    finally:
        for path, original in originals.items():
            if path.read_text(encoding="utf-8") != original:
                path.write_text(original, encoding="utf-8")
        check_nginx()
        reload_nginx()

    raise ValueError(
        f"could not identify the live Nginx server for 127.0.0.1:{port}; "
        "all loaded listening server blocks were probed and none handled the request"
    )


def resolve_file(port: int, web_root: str, preferred: Path | None) -> Path:
    del preferred
    paths = loaded_config_paths(nginx_dump())
    candidates = candidate_blocks(paths, port, web_root)
    return discover_active_candidate(candidates, port).path


def remove_old_dashboard_blocks(text: str) -> str:
    while BEGIN in text:
        start = text.index(BEGIN)
        try:
            finish = text.index(END, start) + len(END)
        except ValueError as exc:
            raise ValueError("incomplete AS1455 dashboard marker block") from exc
        text = text[:start].rstrip() + "\n" + text[finish:].lstrip("\n")
    return text


def dashboard_payload(bazi_port: int, stock_port: int, base: str) -> str:
    return f"""    # BEGIN AS1455 DASHBOARD
    location = /_as1455_portal_auth {{
        internal;
        proxy_pass http://127.0.0.1:{bazi_port}/api/v1/auth/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length \"\";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Host $host;
        proxy_set_header X-Original-URI $request_uri;
    }}

    location = /{base} {{
        return 301 /{base}/;
    }}

    location ^~ /{base}/ {{
        auth_request /_as1455_portal_auth;
        error_page 401 403 =302 /bazi/login?external_redirect=/{base}/;

        proxy_pass http://127.0.0.1:{stock_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection \"upgrade\";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /{base};
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }}
    # END AS1455 DASHBOARD"""


def patch_file(
    path: Path,
    port: int,
    web_root: str,
    bazi_port: int,
    stock_port: int,
    base: str,
) -> None:
    base = base.strip("/")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", base):
        raise ValueError(f"invalid base path: {base!r}")

    resolved = path.resolve()
    loaded_paths = loaded_config_paths(nginx_dump())
    if resolved not in loaded_paths:
        raise ValueError(f"refusing to patch an unloaded Nginx file: {resolved}")

    candidates = [
        candidate
        for candidate in candidate_blocks([resolved], port, web_root)
        if candidate.path == resolved
    ]
    active = discover_active_candidate(candidates, port)

    original = resolved.read_text(encoding="utf-8")
    cleaned = remove_old_dashboard_blocks(original)
    updated = insert_into_block(
        cleaned,
        active.block_index,
        dashboard_payload(bazi_port, stock_port, base),
    )
    resolved.write_text(updated, encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    sub = root.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--port", type=int, required=True)
    resolve.add_argument("--web-root", required=True)
    resolve.add_argument("--preferred")

    patch = sub.add_parser("patch")
    patch.add_argument("--file", type=Path, required=True)
    patch.add_argument("--port", type=int, required=True)
    patch.add_argument("--web-root", required=True)
    patch.add_argument("--bazi-port", type=int, required=True)
    patch.add_argument("--stock-port", type=int, required=True)
    patch.add_argument("--base", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "resolve":
            preferred = Path(args.preferred) if args.preferred else None
            print(resolve_file(args.port, args.web_root, preferred))
        else:
            patch_file(
                args.file,
                args.port,
                args.web_root,
                args.bazi_port,
                args.stock_port,
                args.base,
            )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"as1455_portal_nginx: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
