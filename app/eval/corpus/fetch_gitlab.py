import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

import httpx

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "manifest.json"
FRONT_MATTER = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*\r?\n", re.DOTALL)


class ChecksumMismatch(RuntimeError):
    pass


def strip_front_matter(text: str) -> str:
    return FRONT_MATTER.sub("", text, count=1).lstrip()


def fetch(client: httpx.Client, manifest: dict, target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written = []
    project = quote(manifest["project"], safe="")
    for item in manifest["files"]:
        response = client.get(
            f"{manifest['api_base']}/projects/{project}/repository/files/{quote(item['path'], safe='')}/raw",
            params={"ref": manifest["commit"]},
        )
        response.raise_for_status()
        digest = hashlib.sha256(response.content).hexdigest()
        if digest != item["sha256"]:
            raise ChecksumMismatch(f"{item['path']}: expected sha256 {item['sha256']}, got {digest}")
        path = target / item["name"]
        path.write_text(strip_front_matter(response.content.decode("utf-8")), encoding="utf-8")
        written.append(path)
        print(f"{digest[:12]}  {path}")
    return written


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "groundline-eval-corpus"}) as client:
        fetch(client, manifest, HERE / manifest["output_dir"])
    print(f"{manifest['source']} at {manifest['commit'][:8]}, {manifest['license']}: {manifest['license_url']}")


if __name__ == "__main__":
    main()
