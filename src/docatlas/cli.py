import argparse
import json
import logging
from pathlib import Path

from .config import Settings
from .evaluation import evaluate, markdown_report, regressions
from .ingest import SUPPORTED
from .retrieval import LocalEncoder
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="DocAtlas documentation workspace")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    ingest = commands.add_parser("ingest", help="Index local documents")
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument(
        "--manifest", type=Path, help="Optional filename-to-source-URL JSON mapping"
    )
    ev = commands.add_parser("eval", help="Evaluate retrieval against a labeled JSONL dataset")
    ev.add_argument("dataset", type=Path)
    ev.add_argument("--modes", nargs="+", choices=["bm25", "dense", "hybrid"], default=["bm25"])
    ev.add_argument("--k", type=int, default=5)
    ev.add_argument("--output", type=Path, default=Path("data/eval-report.json"))
    ev.add_argument("--baseline", type=Path)
    ev.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "serve":
        if args.host not in {"127.0.0.1", "localhost", "::1"} and not settings.api_key:
            parser.error("Set DOCATLAS_API_KEY before listening beyond localhost.")
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return
    if settings.embeddings not in {"bm25", "fastembed"}:
        parser.error("DOCATLAS_EMBEDDINGS must be bm25 or fastembed.")
    encoder = (
        LocalEncoder(settings.embedding_model, settings.data_dir / "models")
        if settings.embeddings == "fastembed"
        else None
    )
    store = Store(settings.data_dir, encoder)
    if args.command == "ingest":
        manifest = json.loads(args.manifest.read_text()) if args.manifest else {}
        files = []
        for path in args.paths:
            files.extend(
                sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
                if path.is_dir()
                else [path]
            )
        if len({p.name for p in files}) != len(files):
            parser.error(
                "Duplicate filenames in input. Rename files to keep source identity unambiguous."
            )
        if not files:
            parser.error("No supported documents found.")
        for path in files:
            if path.stat().st_size > settings.max_upload_mb * 1024 * 1024:
                parser.error(f"File too large: {path.name}")
            print(
                json.dumps(
                    {
                        "filename": path.name,
                        **store.ingest(path.name, path.read_bytes(), manifest.get(path.name, "")),
                    }
                )
            )
    elif args.command == "eval":
        if not 1 <= args.k <= 50:
            parser.error("k must be between 1 and 50.")
        report = evaluate(store, args.dataset, args.modes, args.k, settings.min_dense_score)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        args.output.with_suffix(".md").write_text(markdown_report(report))
        print(markdown_report(report))
        if args.baseline:
            failures = regressions(json.loads(args.baseline.read_text()), report, args.tolerance)
            if failures:
                raise SystemExit("Regression gate failed:\n" + "\n".join(failures))


if __name__ == "__main__":
    main()
