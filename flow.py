from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from src.flow_api import (
    FlowApi,
    RUNS_PATH,
    extract_media_items,
    flow_project_url,
    open_chrome_with_extension,
    save_json,
    start_agent,
)


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def downloaded_as_json(downloaded):
    return [
        {
            "media_id": item.media_id,
            "path": str(item.path),
            "width": item.width,
            "height": item.height,
            "source": item.source,
            "size_bytes": item.size_bytes,
        }
        for item in downloaded
    ]


def cmd_start(args):
    try:
        health = FlowApi().health()
        print_json({"already_running": True, "health": health})
        return
    except Exception:
        pass

    process = start_agent()
    print(f"FlowKit agent started, pid={process.pid}")
    if args.wait:
        api = FlowApi()
        for _ in range(30):
            try:
                print_json(api.health())
                return
            except Exception:
                time.sleep(1)
        raise RuntimeError("Agent did not become ready in 30 seconds.")


def cmd_open(args):
    url = args.url or flow_project_url(FlowApi().config.get("project_id"))
    process = open_chrome_with_extension(url)
    print(f"Chrome started, pid={process.pid}")


def cmd_status(args):
    api = FlowApi()
    print_json({"health": api.health(), "flow": api.status()})


def cmd_credits(args):
    api = FlowApi()
    print_json(api.credits())


def cmd_upload(args):
    api = FlowApi()
    result = api.upload_reference(
        args.file,
        name=args.name,
        project_id=args.project_id,
        tags=args.tag,
        note=args.note or "",
    )
    print_json(result)


def cmd_refs(args):
    api = FlowApi()
    if args.name:
        record = api.get_ref(args.name)
        if not record:
            raise SystemExit(f"Reference not found: {args.name}")
        print_json(record)
        return
    print_json(api.list_refs(search=args.search, tag=args.tag))


def cmd_ref_delete(args):
    api = FlowApi()
    deleted = api.delete_ref(args.name)
    print_json({"deleted": deleted, "name": args.name})


def cmd_runs(args):
    if not RUNS_PATH.exists():
        print_json([])
        return
    lines = RUNS_PATH.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines[-args.limit:] if line.strip()]
    print_json(rows)


def cmd_generate(args):
    api = FlowApi()
    refs = args.ref or []
    result = api.generate_images(
        args.prompt,
        count=args.count,
        refs=refs,
        project_id=args.project_id,
        aspect_ratio=args.aspect_ratio,
        user_paygate_tier=args.tier,
        timeout=args.timeout,
    )
    out_dir = Path(args.out_dir) if args.out_dir else None
    downloaded = []
    if args.download:
        downloaded = api.download_media_response(
            result,
            out_dir=out_dir,
            prefix=args.prefix or "flow",
            try_media_api=not args.no_media_api,
            prefer_media_api=args.prefer_media_api,
            quality=args.quality,
            project_id=args.project_id,
            user_paygate_tier=args.tier,
            fallback_preview=args.fallback_preview,
        )
    else:
        response_path = Path(args.response_json or "last_response.json").resolve()
        save_json(response_path, result)

    print_json(
        {
            "media_count": len(extract_media_items(result)) if isinstance(result, dict) else None,
            "downloaded": downloaded_as_json(downloaded),
            "raw": result if args.print_raw else "use --print-raw to print full response",
        }
    )


def cmd_download(args):
    api = FlowApi()
    if args.response_json:
        response_path = Path(args.response_json).expanduser().resolve()
        result = json.loads(response_path.read_text(encoding="utf-8-sig"))
        downloaded = api.download_media_response(
            result,
            out_dir=args.out_dir,
            prefix=args.prefix or response_path.stem,
            try_media_api=not args.no_media_api,
            prefer_media_api=args.prefer_media_api,
            quality=args.quality,
            project_id=args.project_id,
            user_paygate_tier=args.tier,
            fallback_preview=args.fallback_preview,
        )
    else:
        if not args.media_id:
            raise SystemExit("Provide media_id values or --response-json.")
        downloaded = api.download_media_ids(
            args.media_id,
            out_dir=args.out_dir,
            prefix=args.prefix or "media",
            quality=args.quality,
            project_id=args.project_id,
            user_paygate_tier=args.tier,
            fallback_preview=args.fallback_preview,
        )
    print_json({"downloaded": downloaded_as_json(downloaded)})


def cmd_upsample(args):
    api = FlowApi()
    downloaded = api.download_media_ids(
        args.media_id,
        out_dir=args.out_dir,
        prefix=args.prefix or "upsample",
        quality=args.resolution,
        project_id=args.project_id,
        user_paygate_tier=args.tier,
    )
    print_json({"downloaded": downloaded_as_json(downloaded)})


def build_parser():
    parser = argparse.ArgumentParser(description="Local Flow API wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="start bundled FlowKit agent")
    p.add_argument("--wait", action="store_true", help="wait until /health is ready")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("open", help="open Chrome with bundled FlowKit extension")
    p.add_argument("--url", default=None, help="Flow page URL; defaults to configured project page")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("status", help="check local agent and extension")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("credits", help="check Flow credits")
    p.set_defaults(func=cmd_credits)

    p = sub.add_parser("upload", help="upload a reference image and store its media_id")
    p.add_argument("file", help="local image path")
    p.add_argument("--name", help="reference name saved in the local reference library")
    p.add_argument("--project-id", help="Flow project id")
    p.add_argument("--tag", action="append", help="reference tag; repeatable")
    p.add_argument("--note", help="free-form note for this reference")
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("refs", help="list saved reference image media_ids")
    p.add_argument("name", nargs="?", help="show one saved reference by name")
    p.add_argument("--search", help="filter by name, media_id, file path, or note")
    p.add_argument("--tag", help="filter by tag")
    p.set_defaults(func=cmd_refs)

    p = sub.add_parser("ref-delete", help="delete a saved reference mapping")
    p.add_argument("name", help="reference name to delete")
    p.set_defaults(func=cmd_ref_delete)

    p = sub.add_parser("runs", help="show recent generate runs")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_runs)

    p = sub.add_parser("generate", help="generate image(s) via FlowKit extension")
    p.add_argument("prompt", help="image prompt")
    p.add_argument("--count", type=int, default=1, help="number of images, 1-8")
    p.add_argument("--ref", action="append", help="reference name or media_id; repeatable")
    p.add_argument("--project-id", help="Flow project id")
    p.add_argument("--aspect-ratio", default=None, help="landscape, portrait, square, or raw Flow enum")
    p.add_argument("--tier", default=None, help="PAYGATE_TIER_ONE or PAYGATE_TIER_TWO")
    p.add_argument("--timeout", type=int, default=480)
    p.add_argument("--download", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--quality", choices=["preview", "2k", "4k"], default="2k", help="download quality; 2k/4k use Flow upsampleImage")
    p.add_argument("--fallback-preview", action="store_true", help="if 2k/4k upsample fails, save the preview image instead")
    p.add_argument("--no-media-api", action="store_true", help="do not try /api/flow/media fallback")
    p.add_argument("--prefer-media-api", action="store_true", help="try /api/flow/media before the response fifeUrl")
    p.add_argument("--out-dir", help="download output directory")
    p.add_argument("--prefix", help="output filename prefix")
    p.add_argument("--response-json", help="when --no-download, where to save raw response")
    p.add_argument("--print-raw", action="store_true")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("download", help="download images from a response.json or media_id list")
    p.add_argument("media_id", nargs="*", help="media_id values to fetch through /api/flow/media")
    p.add_argument("--response-json", help="download all images from a saved response.json")
    p.add_argument("--out-dir", help="download output directory")
    p.add_argument("--prefix", help="output filename prefix")
    p.add_argument("--quality", choices=["preview", "2k", "4k"], default="2k", help="download quality; 2k/4k use Flow upsampleImage")
    p.add_argument("--fallback-preview", action="store_true", help="if 2k/4k upsample fails, save the preview image instead")
    p.add_argument("--project-id", help="Flow project id for upsampleImage")
    p.add_argument("--tier", default=None, help="PAYGATE_TIER_ONE or PAYGATE_TIER_TWO")
    p.add_argument("--no-media-api", action="store_true", help="do not try /api/flow/media fallback for response.json downloads")
    p.add_argument("--prefer-media-api", action="store_true", help="try /api/flow/media before the response fifeUrl")
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("upsample", help="download media_id values through Flow's 2K/4K image upsample")
    p.add_argument("media_id", nargs="+", help="media_id values to upsample and download")
    p.add_argument("--resolution", choices=["2k", "4k"], default="2k")
    p.add_argument("--project-id", help="Flow project id")
    p.add_argument("--tier", default=None, help="PAYGATE_TIER_ONE or PAYGATE_TIER_TWO")
    p.add_argument("--out-dir", help="download output directory")
    p.add_argument("--prefix", help="output filename prefix")
    p.set_defaults(func=cmd_upsample)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main(sys.argv[1:])
