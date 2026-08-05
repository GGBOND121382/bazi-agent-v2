#!/usr/bin/env python3
"""Locate and patch the loaded Nginx server that serves the shared portal."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
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
    score: int


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


def portal_score(block: str, web_root: str) -> int | None:
    root_match = re.search(r"(?m)^\s*root\s+([^;]+);", block)
    root = root_match.group(1).strip().strip("\"'").rstrip("/") if root_match else ""
    expected_root = web_root.rstrip("/")
    has_root = root == expected_root
    has_portal = bool(
        re.search(r"location\s*=\s*/\s*\{", block)
        and re.search(r"try_files\s+/index\.html", block)
    )
    if not has_root and not has_portal:
        return None
    score = (100 if has_root else 0) + (30 if has_portal else 0)
    if re.search(r"(?m)^\s*listen\s+[^;]*\bdefault_server\b[^;]*;", block):
        score += 10
    return score


def nginx_command(*args: str) -> list[str]:
    command = [os.environ.get("NGINX_BIN", "nginx")]
    prefix = os.environ.get("NGINX_PREFIX", "")
    config = os.environ.get("NGINX_CONFIG", "")
    if prefix:
        command.extend(["-p", prefix])
    if config:
        command.extend(["-c", config])
    command.extend(args)
    return command


def nginx_dump() -> str:
    result = subprocess.run(
        nginx_command("-T"),
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode != 0:
        raise ValueError(output.strip() or f"nginx -T exited with {result.returncode}")
    return output


def loaded_config_paths(dump: str) -> list[Path]:
    paths: list[Path] = []
    for marker in CONFIG_MARKER.finditer(dump):
        path = Path(marker.group(1)).resolve()
        if path.is_file() and path not in paths:
            paths.append(path)
    if not paths:
        raise ValueError("nginx -T did not expose any loaded configuration files")
    return paths


def candidates_in_file(path: Path, port: int, web_root: str) -> list[Candidate]:
    text = path.read_text(encoding="utf-8")
    candidates: list[Candidate] = []
    for block in iter_server_blocks(text):
        if not listens_on_port(block.text, port):
            continue
        score = portal_score(block.text, web_root)
        if score is not None:
            candidates.append(Candidate(path, block.index, score))
    return candidates


def choose_candidate(candidates: list[Candidate], preferred: Path | None = None) -> Candidate:
    if not candidates:
        raise ValueError("no loaded Nginx portal server block matched")
    preferred_resolved = preferred.resolve() if preferred and preferred.exists() else None
    ranked = [
        (
            candidate.score + (1 if preferred_resolved == candidate.path else 0),
            candidate,
        )
        for candidate in candidates
    ]
    best_score = max(score for score, _ in ranked)
    best = [candidate for score, candidate in ranked if score == best_score]
    if len(best) != 1:
        labels = ", ".join(f"{item.path}#server[{item.block_index}]" for item in best)
        raise ValueError(f"multiple equally suitable loaded portal blocks: {labels}")
    return best[0]


def resolve_candidate(port: int, web_root: str, preferred: Path | None) -> Candidate:
    candidates: list[Candidate] = []
    for path in loaded_config_paths(nginx_dump()):
        try:
            candidates.extend(candidates_in_file(path, port, web_root))
        except (OSError, UnicodeError, ValueError):
            continue
    return choose_candidate(candidates, preferred)


def remove_old_dashboard_blocks(text: str) -> str:
    while BEGIN in text:
        start = text.index(BEGIN)
        try:
            finish = text.index(END, start) + len(END)
        except ValueError as exc:
            raise ValueError("incomplete AS1455 dashboard marker block") from exc
        text = text[:start].rstrip() + "\n" + text[finish:].lstrip("\n")
    return text


def insert_into_block(text: str, block_index: int, payload: str) -> str:
    blocks = list(iter_server_blocks(text))
    if block_index < 0 or block_index >= len(blocks):
        raise ValueError(f"server block index {block_index} is no longer valid")
    target = blocks[block_index]
    insert_at = target.end - 1
    return text[:insert_at].rstrip() + "\n\n" + payload.rstrip() + "\n" + text[insert_at:]


def dashboard_payload(bazi_port: int, stock_port: int, base: str) -> str:
    readiness = f"/_as1455_{base}_gateway_ready"
    login_location = f"@as1455_{base}_login"
    return f"""    # BEGIN AS1455 DASHBOARD
    location = {readiness} {{
        add_header X-AS1455-Gateway \"{base}\" always;
        return 204;
    }}

    location = /_as1455_portal_auth {{
        internal;
        proxy_pass http://127.0.0.1:{bazi_port}/api/v1/auth/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length \"\";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Host $host;
        proxy_set_header X-Original-URI $request_uri;
    }}

    location {login_location} {{
        return 302 /bazi/login?external_redirect=/{base}/;
    }}

    location = /{base} {{
        return 301 /{base}/;
    }}

    location ^~ /{base}/ {{
        auth_request /_as1455_portal_auth;
        error_page 401 403 = {login_location};

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

    original = resolved.read_text(encoding="utf-8")
    cleaned = remove_old_dashboard_blocks(original)
    candidates = candidates_in_file(resolved, port, web_root)
    candidate = choose_candidate(candidates)
    updated = insert_into_block(
        cleaned,
        candidate.block_index,
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
            print(resolve_candidate(args.port, args.web_root, preferred).path)
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
