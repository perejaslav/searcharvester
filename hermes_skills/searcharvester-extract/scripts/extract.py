#!/usr/bin/env python3
"""Call the Searcharvester /extract endpoint and print markdown + metadata as JSON."""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def main() -> int:
    p = argparse.ArgumentParser(description="Extract page markdown via Searcharvester")
    p.add_argument("--url", help="Page URL (required unless --id given)")
    p.add_argument("--size", default="m", choices=["s", "m", "l", "f"])
    p.add_argument("--id", dest="extract_id", help="id from previous /extract response")
    p.add_argument("--page", type=int, default=1, help="page number when used with --id (>=1)")
    p.add_argument(
        "--base-url",
        default=os.environ.get("SEARCHARVESTER_URL", "http://tavily-adapter:8000"),
    )
    args = p.parse_args()

    base = args.base_url.rstrip("/")

    if args.extract_id:
        if args.page < 1:
            print(json.dumps({"error": "page must be >= 1"}))
            return 2
        url = f"{base}/extract/{args.extract_id}/{args.page}"
        req = urllib.request.Request(url, method="GET")
    else:
        if not args.url:
            print(json.dumps({"error": "either --url or --id is required"}))
            return 2
        payload = {"url": args.url, "size": args.size}
        req = urllib.request.Request(
            f"{base}/extract",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}", "detail": e.read().decode("utf-8", "replace")}))
        return 1
    except Exception as e:
        print(json.dumps({"error": type(e).__name__, "detail": str(e)}))
        return 1

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
