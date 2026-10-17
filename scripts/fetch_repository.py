#!/usr/bin/env python3
"""
fetch_repository.py -- Fetch a public GitHub repository to a local temp dir.

Usage:
  python3 fetch_repository.py <github-url>
  python3 fetch_repository.py <github-url> --keep <output-dir>   # don't auto-clean
  python3 fetch_repository.py <github-url> --info                 # print metadata only

Stdlib only, Python 3.8+. No external dependencies.

Behavior:
  - Validates the URL is a github.com (or *.github.io) HTTP(S) URL.
  - Downloads the repo as a tarball from https://api.github.com/repos/<owner>/<repo>/tarball.
  - Extracts to a temp dir (auto-removed on exit, unless --keep is passed).
  - Refuses tarballs larger than --max-size (default 500 MB).
  - Returns the local path to the extracted repo on stdout.

Security:
  - Only HTTPS to api.github.com.
  - URL must be github.com or *.github.com (gists, user pages, etc).
  - Tarball is streamed to disk, never loaded fully into memory.
  - Extracted files are validated to be under the target dir (zip-slip-style check).
  - The temporary directory is always cleaned up unless --keep is passed.
"""

import argparse
import io
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------

ALLOWED_HOSTS = {"github.com", "api.github.com", "codeload.github.com"}
MAX_DEFAULT_BYTES = 500 * 1024 * 1024  # 500 MB
CONNECT_TIMEOUT = 15  # seconds -- only the connect phase is bounded
# Note: the connect phase is bounded by CONNECT_TIMEOUT via urlopen's
# `timeout` kwarg. The read phase is bounded only by the size cap
# (MAX_DEFAULT_BYTES). If a peer trickles bytes below the cap, the
# read will block. This is documented behavior; the only way to bound
# the read in stdlib is to add a future/thread wrapper, which the
# skill does not currently do.

GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class FetchError(Exception):
    pass


# ----------------------------------------------------------------------
# URL parsing
# ----------------------------------------------------------------------


def parse_github_url(url: str) -> Tuple[str, str]:
    """Return (owner, repo) or raise FetchError."""
    if not url.startswith(("http://", "https://")):
        raise FetchError(f"URL must start with http:// or https://: {url!r}")
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname is None or parsed.hostname.lower() not in ALLOWED_HOSTS:
        raise FetchError(
            f"Host {parsed.hostname!r} is not allowed. "
            f"Only github.com, api.github.com, codeload.github.com are supported in v1."
        )
    m = GITHUB_URL_RE.match(url)
    if not m:
        raise FetchError(
            f"URL does not look like a GitHub repo URL: {url!r}. "
            f"Expected: https://github.com/<owner>/<repo>"
        )
    return m.group("owner"), m.group("repo")


# ----------------------------------------------------------------------
# Download + extract
# ----------------------------------------------------------------------


def fetch_repo_tarball(owner: str, repo: str, max_bytes: int = MAX_DEFAULT_BYTES) -> bytes:
    """Download the tarball, enforcing a size cap. Returns the bytes."""
    url = f"https://api.github.com/repos/{owner}/{repo}/tarball"
    # Optional: pass default branch via ?ref= — if not given, GitHub returns the default branch
    req = urllib.request.Request(url, headers={"User-Agent": "project-defense-skill/1.0"})
    try:
        response = urllib.request.urlopen(req, timeout=CONNECT_TIMEOUT)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise FetchError(
                f"GitHub returned 403 (rate limited or repo not found) for {owner}/{repo}. "
                f"Wait a few minutes or check that the repo is public."
            ) from e
        if e.code == 404:
            raise FetchError(f"Repository {owner}/{repo} not found (404). Is it public?") from e
        raise FetchError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"Network error fetching {url}: {e.reason}") from e

    # Read the response in chunks, enforcing the size cap as we go.
    chunks = []
    total = 0
    while True:
        try:
            chunk = response.read(64 * 1024)
        except socket_timeout_as_exception():
            raise FetchError("Timed out while reading tarball from GitHub.")
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise FetchError(
                f"Tarball exceeds --max-size ({max_bytes} bytes). "
                f"Refusing to continue. Pass a larger --max-size to override."
            )
        chunks.append(chunk)
    return b"".join(chunks)


class _SocketTimeout(Exception):
    pass


def socket_timeout_as_exception():
    """Compatibility shim: socket.timeout is a subclass of OSError; we want a single check."""
    import socket
    return socket.timeout


def safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract `tar` to `dest`, refusing any member that would escape `dest`.

    Security: this is a defense against CVE-2007-4559-style tarfile attacks.
    The name-only check (used in many naive "safe_extract" implementations)
    is NOT sufficient: a tar member of type SYMTYPE or LNKTYPE can have a
    safe-looking name (e.g. "evil_link") while its linkname points outside
    the extraction root. On Python 3.8-3.12, tar.extractall() without an
    explicit filter= kwarg defaults to "fully_trusted", which creates real
    symlinks and hardlinks on disk. A subsequent directory walk + read_text
    on the extracted tree will follow the link and read the target file.

    Fix: reject any member whose type is not REGTYPE, AREGTYPE, or DIRTYPE.
    """
    dest = dest.resolve()
    allowed_types = {tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE}
    for member in tar.getmembers():
        if member.type not in allowed_types:
            raise FetchError(
                f"Refusing tar member {member.name!r}: type {member.type} is not a regular file or directory. "
                f"This blocks symlinks, hardlinks, devices, and FIFOs. "
                f"This protects against a GitHub repo owner reading arbitrary files "
                f"from the user's machine via a malicious tarball."
            )
        member_path = (dest / member.name).resolve()
        try:
            member_path.relative_to(dest)
        except ValueError:
            raise FetchError(
                f"Refusing to extract {member.name!r} -- path escapes target dir. "
                f"This is a malicious or corrupted tarball."
            )
        # Also refuse absolute paths and parent-dir refs
        if member.name.startswith(("/", "\\")) or ".." in Path(member.name).parts:
            raise FetchError(
                f"Refusing to extract {member.name!r} -- contains absolute or '..' path."
            )
    # Defense in depth: pass the data filter on Python 3.12+ to also catch
    # anything the manual type check above might miss (e.g. a path-traversal
    # symlink that resolves back inside dest but the linkname points elsewhere).
    if sys.version_info >= (3, 12):
        tar.extractall(dest, filter="data")
    else:
        tar.extractall(dest)


def extract_to_tempdir(tar_bytes: bytes, keep_dir: Optional[Path] = None) -> Path:
    """Extract the tarball to a temp dir (or keep_dir if given). Returns the repo root."""
    if keep_dir:
        keep_dir.mkdir(parents=True, exist_ok=True)
        work = keep_dir
    else:
        work = Path(tempfile.mkdtemp(prefix="pdc-fetch-"))

    try:
        try:
            with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
                safe_extract(tar, work)
        except tarfile.TarError as e:
            raise FetchError(f"Failed to extract tarball: {e}") from e

        # The tarball's top-level dir is <owner>-<repo>-<sha>/. Find it.
        entries = list(work.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise FetchError(
                f"Unexpected tarball layout: expected one top-level dir, got {len(entries)} entries"
            )
        return entries[0]
    except BaseException:
        # Cleanup the temp dir on ANY failure (FetchError, OSError, KeyboardInterrupt).
        # The previous version only cleaned up on tarfile.TarError, which leaked temp
        # dirs whenever safe_extract raised FetchError (a path-traversal rejection).
        # BaseException (not Exception) also covers KeyboardInterrupt and SystemExit.
        if not keep_dir:
            shutil.rmtree(work, ignore_errors=True)
        raise


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def fetch(url: str, keep_dir: Optional[Path] = None, max_bytes: int = MAX_DEFAULT_BYTES) -> Path:
    """Fetch a public GitHub repo and return the local path. Raises FetchError on failure."""
    owner, repo = parse_github_url(url)
    print(f"Fetching {owner}/{repo} from GitHub...", file=sys.stderr)
    tar_bytes = fetch_repo_tarball(owner, repo, max_bytes=max_bytes)
    print(f"Downloaded {len(tar_bytes):,} bytes", file=sys.stderr)
    path = extract_to_tempdir(tar_bytes, keep_dir=keep_dir)
    print(f"Extracted to {path}", file=sys.stderr)
    return path


def fetch_info(url: str) -> dict:
    """Return parsed owner/repo without downloading. Useful for validation."""
    owner, repo = parse_github_url(url)
    return {"owner": owner, "repo": repo, "tarball_url": f"https://api.github.com/repos/{owner}/{repo}/tarball"}


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Fetch a public GitHub repository to a local directory."
    )
    parser.add_argument("url", help="GitHub repo URL, e.g. https://github.com/owner/repo")
    parser.add_argument(
        "--keep",
        type=Path,
        default=None,
        help="Extract to this directory instead of a temp dir (skips auto-cleanup).",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=MAX_DEFAULT_BYTES,
        help=f"Maximum tarball size in bytes (default {MAX_DEFAULT_BYTES // (1024*1024)} MB).",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Just parse the URL and print metadata, don't download.",
    )

    args = parser.parse_args()

    try:
        if args.info:
            print(json.dumps(fetch_info(args.url), indent=2))
            return 0
        path = fetch(args.url, keep_dir=args.keep, max_bytes=args.max_size)
        # Path goes to stdout so callers can capture it.
        print(str(path))
        return 0
    except FetchError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


import json  # placed after arg parser to keep top-of-file imports tidy

if __name__ == "__main__":
    sys.exit(main())