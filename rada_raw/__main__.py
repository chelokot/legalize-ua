import argparse
import hashlib
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from rada_raw.client import Blocked, Pacer, RadaClient, Response, Unavailable
from rada_raw.dumps import Edition, download, read_documents, read_editions
from rada_raw.manifest import Manifest, Record, edition_path
from rada_raw.plan import plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mirror Verkhovna Rada legislation editions into raw/")
    parser.add_argument("--root", type=Path, default=Path("raw"))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-requests", type=int, default=0, help="0 means no limit")
    parser.add_argument("--deadline-seconds", type=int, default=19200)
    parser.add_argument("--rate", type=float, default=1.0, help="starting requests per second")
    parser.add_argument("--max-rate", type=float, default=1.5)
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def commit_and_push(paths: list[Path], message: str) -> None:
    subprocess.run(["git", "add", "--sparse", "--all", *map(str, paths)], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "--quiet", "--message", message], check=True)
    for _ in range(3):
        if subprocess.run(["git", "push", "--quiet"]).returncode == 0:
            return
        subprocess.run(["git", "pull", "--rebase", "--quiet"], check=True)
    raise RuntimeError("git push failed three times")


def store(root: Path, manifest: Manifest, edition: Edition, response: Response) -> None:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if response.status == 200:
        path = edition_path(root, edition.nreg, edition.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.body)
        digest = hashlib.sha256(response.body).hexdigest()
    else:
        digest = ""
    manifest.put(Record(edition.nreg, edition.date, edition.modified, response.status, digest, len(response.body), fetched_at))


def write_outputs(**values: int) -> None:
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as output:
        for name, value in values.items():
            output.write(f"{name}={value}\n")


def main() -> int:
    args = parse_args()
    deadline = time.monotonic() + args.deadline_seconds
    dumps_directory = args.root / "dumps"
    pacer = Pacer(args.rate, args.max_rate)
    client = RadaClient(pacer)
    blocked = threading.Event()

    def fetch(edition: Edition) -> tuple[Edition, Response | None]:
        if blocked.is_set():
            return edition, None
        try:
            return edition, client.get(f"/laws/show/{quote(edition.nreg, safe='/')}/ed{edition.date}")
        except Unavailable:
            return edition, None
        except Blocked:
            blocked.set()
            return edition, None

    download(client, dumps_directory)
    commit_and_push([dumps_directory], "Update Rada open data dumps")
    documents = read_documents(dumps_directory)
    editions, malformed = read_editions(dumps_directory)
    manifest = Manifest(args.root / "manifest")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    queue = plan(documents, editions, manifest, today)
    if args.max_requests:
        queue = queue[: args.max_requests]
    print(f"{len(documents)} documents, {len(editions)} editions ({len(malformed)} malformed), {len(queue)} to fetch", flush=True)

    stored = 0
    skipped = 0
    with ThreadPoolExecutor(args.workers) as pool:
        for start in range(0, len(queue), args.batch_size):
            if time.monotonic() > deadline or blocked.is_set():
                break
            for edition, response in pool.map(fetch, queue[start : start + args.batch_size]):
                if response is None:
                    skipped += 1
                else:
                    store(args.root, manifest, edition, response)
                    stored += 1
            manifest.save()
            left = len(plan(documents, editions, manifest, today))
            commit_and_push([args.root / "docs", args.root / "manifest"], f"Mirror Rada editions: {stored} stored, {left} left")
            print(f"stored {stored}, skipped {skipped}, {left} left, {pacer.rate:.2f} req/s", flush=True)

    remaining = len(plan(documents, editions, manifest, today))
    write_outputs(stored=stored, remaining=remaining)
    if blocked.is_set():
        print("Rada blocked our IP (HTTP 403), stopped early", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
