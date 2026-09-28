"""Download a fixed public FastAPI documentation snapshot, never private documents."""

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "evals/corpus-manifest.json").read_text())
    destination = ROOT / "data/corpus"
    destination.mkdir(parents=True, exist_ok=True)
    for doc in manifest["documents"]:
        request = urllib.request.Request(
            doc["download_url"], headers={"User-Agent": "DocAtlas-corpus-builder"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read(2_000_001)
        if len(content) > 2_000_000:
            raise ValueError("Document exceeds the download limit.")
        if hashlib.sha256(content).hexdigest() != doc["sha256"]:
            raise ValueError(f"Corpus checksum mismatch: {doc['filename']}")
        (destination / doc["filename"]).write_bytes(content)
        print(doc["filename"])
    (ROOT / "data/corpus-sources.json").write_text(
        json.dumps({d["filename"]: d["source_url"] for d in manifest["documents"]}, indent=2)
    )


if __name__ == "__main__":
    main()
