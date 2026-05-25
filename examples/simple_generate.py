from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.flow_api import FlowApi


def main() -> None:
    api = FlowApi()
    result = api.generate_images(
        "cinematic macro futuristic city core, ultra detailed, realistic lighting",
        count=1,
        aspect_ratio="landscape",
    )
    downloaded = api.download_media_response(result, prefix="python-demo")
    for item in downloaded:
        print(f"{item.path} | {item.width}x{item.height} | {item.media_id}")


if __name__ == "__main__":
    main()
