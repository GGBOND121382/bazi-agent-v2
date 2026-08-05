#!/usr/bin/env python3
"""Locate and patch the Nginx server that serves the shared portal."""
from __future__ import annotations

import argparse
import glob
import re
import sys
from dataclasses import dataclass
from pathlib import Path

BEGIN = "    # BEGIN AS1455 DASHBOARD"
END = "    # END AS1455 DASHBOARD"


@dataclass(frozen=True)
class ServerBlock:
    start: int
    end: int
    text: str
    score: int


def mask_comments(text: str) -> str:
    return re.sub(r"(?m)#.*$", lambda match: " " * len(match.group(0)), text)


def iter_server_ranges(text: str):
    masked = mask_comments(text)
    for match in re.finditer(r"\bserver\s*\{", masked):
        brace_start = masked.find("{", match.start(), match.end())
        depth = 0
        for index in range(brace_start, len(masked)):
            if masked[index] == "{":
                depth += 1
            elif masked[index] == "}":
                depth -= 1
                if depth == 0:
                    yield match.start(), index + 1
                    break


def block_score(block: str, port: int, web_root: str) -> int | None:
    listen = re.search(
        rf"(?m)^\s*listen\s+(?:(?:\[[^]]+\]|[A-Za-z0-9.*_-]+):)?{port}(?:\s|;)",
        block,
    )
    if not listen:
        return None
    root_match = re.search(r"(?m)^\s*root\s+([^;]+);", block)
    root = root_match.group(1).strip().strip("\"'").rstrip("/") if root_match else ""
    has_root = root == web_root.rstrip("/")
    has_portal = bool(
        re.search(r"location\s*=\s*/\s*\{", block)
        and re.search(r"try_files\s+/index\.html", block)
    )
    score = (100 if has_root else 0) + (30 if has_portal else 0)
    if "default_server" in listen.group(0):
        score += 10
    return score


def best_block(text: str, port: int, web_root: str) -> ServerBlock:
    matches: list[ServerBlock] = []
    for start, end in iter_server_ranges(text):
        block = text[start:end]
        score = block_score(block, port, web_root)
        if score is not None and score > 0:
            matches.append(ServerBlock(start, end, block, score))
    if not matches:
        raise ValueError(f"no server listens on {port} and serves {web_root}")
    best_score = max(item.score for item in matches)
    best = [item for item in matches if item.score == best_score]
    if len(best) != 1:
        raise ValueError(f"found {len(best)} equally suitable portal server blocks")
    return best[0]


def candidate_files(preferred: Path | None) -> list[Path]:
    result: list[Path] = []
    for pattern in ("/etc/nginx/sites-enabled/*", "/etc/nginx/conf.d/*.conf"):
        for value in glob.glob(pattern):
            path = Path(value).resolve()
            if path.is_file() and path not in result:
                result.append(path)
    if preferred and preferred.is_file():
        path = preferred.resolve()
        if path not in result:
            result.append(path)
    return result


def resolve_file(port: int, web_root: str, preferred: Path | None) -> Path:
    matches: list[tuple[int, Path]] = []
    candidates = candidate_files(preferred)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
            block = best_block(text, port, web_root)
        except (OSError, UnicodeError, ValueError):
            continue
        matches.append((block.score, path))
    if not matches:
        searched = ", ".join(str(path) for path in candidates) or "<none>"
        raise ValueError(
            f"cannot find an enabled portal server for port={port}, root={web_root}; "
            f"searched: {searched}"
        )
    score = max(item[0] for item in matches)
    paths = sorted({path for item_score, path in matches if item_score == score})
    if len(paths) != 1:
        raise ValueError("multiple portal config files match: " + ", ".join(map(str, paths)))
    return paths[0]


def remove_old_blocks(text: str) -> str:
    while BEGIN in text:
        start = text.index(BEGIN)
        try:
            finish = text.index(END, start) + len(END)
        except ValueError as exc:
            raise ValueError("incomplete AS1455 marker block") from exc
        text = text[:start].rstrip() + "\n" + text[finish:].lstrip("\n")
    return text


def patch_file(
    path: Path,
    port: int,
    web_root: str,
    bazi_port: int,
    stock_port: int,
    base: str,
) -> None:
    text = remove_old_blocks(path.read_text(encoding="utf-8"))
    target = best_block(text, port, web_root)
    block = f"""    # BEGIN AS1455 DASHBOARD
    location = /_as1455_portal_auth {{
        internal;
        proxy_pass http://127.0.0.1:{bazi_port}/api/v1/auth/me;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
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
        proxy_set_header Connection "upgrade";
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
    insert_at = target.end - 1
    updated = text[:insert_at] + "\n\n" + block + "\n" + text[insert_at:]
    path.write_text(updated, encoding="utf-8")


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
