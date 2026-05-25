from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from .ref_store import RefStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"
CONFIG_EXAMPLE_PATH = PROJECT_ROOT / "config.example.json"
STATE_DIR = PROJECT_ROOT / "state"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
REFS_PATH = STATE_DIR / "refs.json"
REF_DB_PATH = STATE_DIR / "flow_tool.sqlite"
RUNS_PATH = STATE_DIR / "runs.jsonl"
VENDOR_FLOWKIT = PROJECT_ROOT / "vendor" / "flowkit"


ASPECT_RATIOS = {
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
    "square": "IMAGE_ASPECT_RATIO_SQUARE",
}

UPSAMPLE_RESOLUTIONS = {
    "2k": "UPSAMPLE_IMAGE_RESOLUTION_2K",
    "4k": "UPSAMPLE_IMAGE_RESOLUTION_4K",
    "UPSAMPLE_IMAGE_RESOLUTION_2K": "UPSAMPLE_IMAGE_RESOLUTION_2K",
    "UPSAMPLE_IMAGE_RESOLUTION_4K": "UPSAMPLE_IMAGE_RESOLUTION_4K",
}

DOWNLOAD_QUALITIES = {"preview", "2k", "4k"}


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dirs() -> None:
    for path in (STATE_DIR, OUTPUT_DIR, PROJECT_ROOT / "logs", PROJECT_ROOT / "refs"):
        path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config() -> dict[str, Any]:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        if CONFIG_EXAMPLE_PATH.exists():
            shutil.copy2(CONFIG_EXAMPLE_PATH, CONFIG_PATH)
        else:
            save_json(CONFIG_PATH, {})
    cfg = load_json(CONFIG_PATH, {})
    cfg.setdefault("base_url", "http://127.0.0.1:8100")
    cfg.setdefault("project_id", "")
    cfg.setdefault("user_paygate_tier", "PAYGATE_TIER_ONE")
    cfg.setdefault("aspect_ratio", "IMAGE_ASPECT_RATIO_LANDSCAPE")
    cfg.setdefault("chrome_path", "")
    cfg.setdefault("chrome_profile_dir", str(PROJECT_ROOT / "chrome-profile"))
    return cfg


def append_run(record: dict[str, Any]) -> None:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def slugify(text: str, default: str = "flow") -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.strip(), flags=re.UNICODE)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:60] or default


def normalize_aspect_ratio(value: str | None) -> str:
    if not value:
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"
    return ASPECT_RATIOS.get(value.lower(), value)


def normalize_download_quality(value: str | None) -> str:
    if not value:
        return "2k"
    normalized = value.strip().lower()
    if normalized in {"original", "default"}:
        return "preview"
    if normalized not in DOWNLOAD_QUALITIES:
        raise ValueError("quality must be preview, 2k, or 4k")
    return normalized


def normalize_upsample_resolution(value: str | None) -> str:
    if not value:
        return UPSAMPLE_RESOLUTIONS["2k"]
    key = value.strip()
    return UPSAMPLE_RESOLUTIONS.get(key.lower(), UPSAMPLE_RESOLUTIONS.get(key, key))


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def image_extension_from_bytes(content: bytes, fallback: str = ".jpg") -> str:
    try:
        with Image.open(BytesIO(content)) as img:
            fmt = (img.format or "").lower()
    except Exception:
        return fallback
    return {
        "jpeg": ".jpg",
        "jpg": ".jpg",
        "png": ".png",
        "webp": ".webp",
        "gif": ".gif",
    }.get(fmt, fallback)


def extract_media_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    media = data.get("media")
    if isinstance(media, list):
        return media
    if isinstance(media, dict):
        return [media]
    raw = data.get("raw")
    if isinstance(raw, dict):
        return extract_media_items(raw)
    return []


def media_id_from_item(item: dict[str, Any]) -> str:
    return (
        item.get("name")
        or item.get("mediaId")
        or item.get("image", {}).get("generatedImage", {}).get("mediaId")
        or ""
    )


def fife_url_from_item(item: dict[str, Any]) -> str:
    image = item.get("image", {})
    generated = image.get("generatedImage", {}) if isinstance(image, dict) else {}
    return (
        generated.get("fifeUrl")
        or generated.get("imageUri")
        or item.get("fifeUrl")
        or item.get("servingUri")
        or ""
    )


def _decode_image_base64(value: str) -> bytes | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("data:image/") and "," in raw:
        raw = raw.split(",", 1)[1]
    raw = re.sub(r"\s+", "", raw)
    if len(raw) < 80:
        return None
    try:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=True)
    except Exception:
        return None
    try:
        with Image.open(BytesIO(decoded)) as img:
            img.verify()
    except Exception:
        return None
    return decoded


def extract_image_bytes(data: Any) -> tuple[bytes | None, str | None]:
    """Find image bytes in nested Flow responses."""
    preferred_keys = {
        "rawBytes",
        "imageBase64Bytes",
        "encodedImage",
        "imageBytes",
        "b64_json",
    }
    if isinstance(data, dict):
        for key in preferred_keys:
            decoded = _decode_image_base64(data.get(key))
            if decoded:
                return decoded, key
        for key, value in data.items():
            decoded, source = extract_image_bytes(value)
            if decoded:
                return decoded, source or key
    elif isinstance(data, list):
        for item in data:
            decoded, source = extract_image_bytes(item)
            if decoded:
                return decoded, source
    return None, None


def extract_download_url(data: Any) -> str:
    if isinstance(data, dict):
        for key in ("fifeUrl", "servingUri", "imageUri", "url", "downloadUrl"):
            value = data.get(key)
            if isinstance(value, str) and value.startswith("https://"):
                return value
        for value in data.values():
            url = extract_download_url(value)
            if url:
                return url
    elif isinstance(data, list):
        for item in data:
            url = extract_download_url(item)
            if url:
                return url
    return ""


def flow_project_url(project_id: str | None) -> str:
    if project_id:
        return f"https://labs.google/fx/zh/tools/flow/project/{project_id}"
    return "https://labs.google/fx/zh/tools/flow"


def unique_keep_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


@dataclass
class DownloadedImage:
    media_id: str
    path: Path
    width: int | None
    height: int | None
    source: str
    size_bytes: int


class FlowApi:
    def __init__(self, base_url: str | None = None):
        self.config = load_config()
        self.base_url = (base_url or self.config["base_url"]).rstrip("/")
        self.session = requests.Session()
        self.refs = RefStore(REF_DB_PATH, REFS_PATH)

    def health(self) -> dict[str, Any]:
        return self.session.get(f"{self.base_url}/health", timeout=20).json()

    def status(self) -> dict[str, Any]:
        return self.session.get(f"{self.base_url}/api/flow/status", timeout=20).json()

    def credits(self) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}/api/flow/credits", timeout=30)
        response.raise_for_status()
        return response.json()

    def upload_reference(
        self,
        file_path: str | Path,
        name: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        src = Path(file_path).expanduser().resolve()
        if not src.exists():
            raise FileNotFoundError(src)
        project_id = project_id or self.config.get("project_id")
        if not project_id:
            raise ValueError("project_id is required. Set it in config.json or pass project_id.")

        response = self.session.post(
            f"{self.base_url}/api/flow/upload-image",
            json={
                "file_path": str(src),
                "project_id": project_id,
                "file_name": src.name,
            },
            timeout=180,
        )
        response.raise_for_status()
        result = response.json()
        media_id = result.get("media_id")
        if not media_id:
            raise RuntimeError(f"Upload succeeded but no media_id was returned: {result}")

        ref_name = name or src.stem
        return self.refs.upsert(
            name=ref_name,
            media_id=media_id,
            file_path=str(src),
            project_id=project_id,
            raw=result,
            tags=tags,
            note=note,
        )

    def list_refs(self, search: str | None = None, tag: str | None = None) -> list[dict[str, Any]]:
        return self.refs.list(search=search, tag=tag)

    def get_ref(self, name: str) -> dict[str, Any] | None:
        return self.refs.get(name)

    def delete_ref(self, name: str) -> bool:
        return self.refs.delete(name)

    def resolve_refs(self, refs: list[str] | None) -> list[str]:
        if not refs:
            return []
        resolved = []
        for ref in refs:
            resolved.append(self.refs.resolve(ref))
        return unique_keep_order(resolved)

    def extract_prompt_refs(self, prompt: str) -> tuple[str, list[str]]:
        """Resolve @reference mentions in prompt text into Flow media IDs.

        Supports @name and @[name with spaces]. Only saved reference names are
        removed from the text; unknown @mentions stay untouched.
        """
        found: list[str] = []

        def replace_ref(match: re.Match) -> str:
            name = (match.group(1) or match.group(2) or "").strip()
            record = self.refs.get(name)
            if not record:
                return match.group(0)
            found.append(record["media_id"])
            return ""

        prompt = re.sub(
            r"@\[([^\]]+)\]|(?<![\w.])@([\w\u4e00-\u9fff.-]+)",
            replace_ref,
            prompt,
            flags=re.UNICODE,
        )
        prompt = re.sub(r"\s{2,}", " ", prompt).strip()
        return prompt, unique_keep_order(found)

    def generate_images(
        self,
        prompt: str,
        *,
        count: int = 1,
        refs: list[str] | None = None,
        project_id: str | None = None,
        aspect_ratio: str | None = None,
        user_paygate_tier: str | None = None,
        timeout: int = 480,
    ) -> dict[str, Any]:
        project_id = project_id or self.config.get("project_id")
        if not project_id:
            raise ValueError("project_id is required. Set it in config.json or pass project_id.")
        prompt, prompt_ref_ids = self.extract_prompt_refs(prompt)
        payload: dict[str, Any] = {
            "project_id": project_id,
            "prompt": prompt,
            "aspect_ratio": normalize_aspect_ratio(aspect_ratio or self.config.get("aspect_ratio")),
            "user_paygate_tier": user_paygate_tier or self.config.get("user_paygate_tier", "PAYGATE_TIER_ONE"),
            "count": max(1, min(int(count), 8)),
        }
        ref_ids = unique_keep_order(prompt_ref_ids + self.resolve_refs(refs))
        if ref_ids:
            payload["character_media_ids"] = ref_ids

        response = self.session.post(
            f"{self.base_url}/api/flow/generate-image",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        append_run(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "type": "generate_images",
                "payload": payload,
                "media_ids": [media_id_from_item(item) for item in extract_media_items(data)],
            }
        )
        return data

    def upsample_image(
        self,
        media_id: str,
        *,
        project_id: str | None = None,
        target_resolution: str | None = "2k",
        user_paygate_tier: str | None = None,
        timeout: int = 360,
    ) -> dict[str, Any]:
        if not media_id:
            raise ValueError("media_id is required")
        payload = {
            "media_id": media_id,
            "project_id": project_id or self.config.get("project_id", ""),
            "target_resolution": normalize_upsample_resolution(target_resolution),
            "user_paygate_tier": user_paygate_tier or self.config.get("user_paygate_tier", "PAYGATE_TIER_ONE"),
        }
        response = self.session.post(
            f"{self.base_url}/api/flow/upsample-image",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        append_run(
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "type": "upsample_image",
                "payload": payload,
            }
        )
        return data

    def _download_from_upsample_response(self, response_data: dict[str, Any]) -> tuple[bytes | None, str]:
        content, source = extract_image_bytes(response_data)
        if content:
            return content, f"flow_upsample:{source}"
        url = extract_download_url(response_data)
        if url:
            content = self._download_url(url)
            if content:
                return content, "flow_upsample:url"
        return None, "flow_upsample:empty"

    def download_upsampled_image(
        self,
        media_id: str,
        *,
        out_dir: str | Path | None = None,
        prefix: str | None = None,
        target_resolution: str | None = "2k",
        project_id: str | None = None,
        user_paygate_tier: str | None = None,
        index: int = 1,
    ) -> DownloadedImage:
        out_path = Path(out_dir) if out_dir else OUTPUT_DIR / f"upsample-{now_stamp()}"
        out_path.mkdir(parents=True, exist_ok=True)
        prefix = slugify(prefix or "upsample")
        safe_media_id = slugify(media_id, f"media-{index}")
        quality = normalize_download_quality(target_resolution)
        response_data = self.upsample_image(
            media_id,
            project_id=project_id,
            target_resolution=quality,
            user_paygate_tier=user_paygate_tier,
        )
        save_json(out_path / f"{prefix}-{index:02d}-{safe_media_id}-upsample-response.json", response_data)
        content, source = self._download_from_upsample_response(response_data)
        if content is None:
            raise RuntimeError(f"Flow upsample did not return downloadable image bytes for media_id={media_id}: {response_data}")
        ext = image_extension_from_bytes(content)
        path = out_path / f"{prefix}-{index:02d}-{safe_media_id}-{quality}{ext}"
        path.write_bytes(content)
        size = image_size(path)
        return DownloadedImage(
            media_id=media_id,
            path=path,
            width=size[0] if size else None,
            height=size[1] if size else None,
            source=source,
            size_bytes=len(content),
        )

    def download_media_response(
        self,
        response_data: dict[str, Any],
        *,
        out_dir: str | Path | None = None,
        prefix: str | None = None,
        try_media_api: bool = True,
        prefer_media_api: bool = False,
        quality: str | None = "2k",
        project_id: str | None = None,
        user_paygate_tier: str | None = None,
        fallback_preview: bool = False,
    ) -> list[DownloadedImage]:
        out_path = Path(out_dir) if out_dir else OUTPUT_DIR / now_stamp()
        out_path.mkdir(parents=True, exist_ok=True)
        prefix = slugify(prefix or "flow")
        quality = normalize_download_quality(quality)
        save_json(out_path / "response.json", response_data)

        downloaded: list[DownloadedImage] = []
        errors: list[dict[str, str]] = []
        for index, item in enumerate(extract_media_items(response_data), 1):
            media_id = media_id_from_item(item) or f"item-{index}"
            url = fife_url_from_item(item)
            safe_media_id = slugify(media_id, f"item-{index}")

            source = ""
            content: bytes | None = None
            if quality != "preview" and media_id:
                try:
                    upsampled = self.download_upsampled_image(
                        media_id,
                        out_dir=out_path,
                        prefix=prefix,
                        target_resolution=quality,
                        project_id=project_id,
                        user_paygate_tier=user_paygate_tier,
                        index=index,
                    )
                    downloaded.append(upsampled)
                    continue
                except Exception as exc:
                    errors.append({"media_id": media_id, "error": str(exc)})
                    if not fallback_preview:
                        (out_path / f"{prefix}-{index:02d}-{safe_media_id}.error.txt").write_text(
                            f"Flow {quality} upsample failed for media_id={media_id}: {exc}\n",
                            encoding="utf-8",
                        )
                        continue

            if prefer_media_api and try_media_api:
                content = self._download_via_media_api(media_id)
                source = "media_api"

            if content is None and url:
                content = self._download_url(url)
                source = "fifeUrl"

            if content is None and try_media_api:
                content = self._download_via_media_api(media_id)
                source = "media_api"

            if content is None:
                (out_path / f"{prefix}-{index:02d}-{media_id}.error.txt").write_text(
                    f"No downloadable URL or encoded image for media_id={media_id}\n",
                    encoding="utf-8",
                )
                errors.append({"media_id": media_id, "error": "No downloadable URL or encoded image"})
                continue

            ext = image_extension_from_bytes(content)
            path = out_path / f"{prefix}-{index:02d}-{safe_media_id}{ext}"
            path.write_bytes(content)
            size = image_size(path)
            downloaded.append(
                DownloadedImage(
                    media_id=media_id,
                    path=path,
                    width=size[0] if size else None,
                    height=size[1] if size else None,
                    source=source,
                    size_bytes=len(content),
                )
            )

        manifest = {
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(downloaded),
            "items": [
                {
                    "media_id": item.media_id,
                    "path": str(item.path),
                    "width": item.width,
                    "height": item.height,
                    "source": item.source,
                    "size_bytes": item.size_bytes,
                }
                for item in downloaded
            ],
            "quality": quality,
            "errors": errors,
            "note": "quality=2k/4k uses Flow's upsampleImage endpoint; quality=preview uses the generated preview URL/media API.",
        }
        save_json(out_path / "download_manifest.json", manifest)
        return downloaded

    def download_media_ids(
        self,
        media_ids: list[str],
        *,
        out_dir: str | Path | None = None,
        prefix: str | None = None,
        quality: str | None = "2k",
        project_id: str | None = None,
        user_paygate_tier: str | None = None,
        fallback_preview: bool = False,
    ) -> list[DownloadedImage]:
        out_path = Path(out_dir) if out_dir else OUTPUT_DIR / f"media-{now_stamp()}"
        out_path.mkdir(parents=True, exist_ok=True)
        prefix = slugify(prefix or "media")
        quality = normalize_download_quality(quality)

        downloaded: list[DownloadedImage] = []
        errors: list[dict[str, str]] = []
        for index, media_id in enumerate(media_ids, 1):
            if quality != "preview":
                try:
                    downloaded.append(
                        self.download_upsampled_image(
                            media_id,
                            out_dir=out_path,
                            prefix=prefix,
                            target_resolution=quality,
                            project_id=project_id,
                            user_paygate_tier=user_paygate_tier,
                            index=index,
                        )
                    )
                    continue
                except Exception as exc:
                    errors.append({"media_id": media_id, "error": str(exc)})
                    if not fallback_preview:
                        safe_media_id = slugify(media_id, f"media-{index}")
                        (out_path / f"{prefix}-{index:02d}-{safe_media_id}.error.txt").write_text(
                            f"Flow {quality} upsample failed for media_id={media_id}: {exc}\n",
                            encoding="utf-8",
                        )
                        continue

            content = self._download_via_media_api(media_id)
            if content is None:
                errors.append(
                    {
                        "media_id": media_id,
                        "error": "Could not download via Flow upsample or /api/flow/media. If this is an image generated in a previous response, use the saved response.json so the signed fifeUrl can be used.",
                    }
                )
                continue
            safe_media_id = slugify(media_id, f"media-{index}")
            ext = image_extension_from_bytes(content)
            path = out_path / f"{prefix}-{index:02d}-{safe_media_id}{ext}"
            path.write_bytes(content)
            size = image_size(path)
            downloaded.append(
                DownloadedImage(
                    media_id=media_id,
                    path=path,
                    width=size[0] if size else None,
                    height=size[1] if size else None,
                    source="media_api",
                    size_bytes=len(content),
                )
            )

        save_json(
            out_path / "download_manifest.json",
            {
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
                "count": len(downloaded),
                "items": [
                    {
                        "media_id": item.media_id,
                        "path": str(item.path),
                        "width": item.width,
                        "height": item.height,
                        "source": item.source,
                        "size_bytes": item.size_bytes,
                    }
                    for item in downloaded
                ],
                "quality": quality,
                "errors": errors,
            },
        )
        return downloaded

    def _download_url(self, url: str, retries: int = 3) -> bytes | None:
        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(url, timeout=180)
                if response.ok and response.content:
                    return response.content
            except requests.RequestException:
                pass
            time.sleep(1.5 * attempt)
        return None

    def _download_via_media_api(self, media_id: str) -> bytes | None:
        if not media_id:
            return None
        try:
            response = self.session.get(f"{self.base_url}/api/flow/media/{media_id}", timeout=120)
            if not response.ok:
                return None
            data = response.json()
        except Exception:
            return None

        encoded = None
        image = data.get("image") if isinstance(data, dict) else None
        if isinstance(image, dict):
            encoded = image.get("encodedImage")
        if isinstance(data, dict):
            encoded = encoded or data.get("encodedImage")
        if encoded:
            try:
                return base64.b64decode(encoded)
            except Exception:
                return None

        url = None
        if isinstance(data, dict):
            url = data.get("fifeUrl") or data.get("servingUri") or data.get("imageUri")
        if url:
            return self._download_url(url)
        return None


def start_agent() -> subprocess.Popen:
    """Start bundled FlowKit agent in the background."""
    work = VENDOR_FLOWKIT
    if not work.exists():
        raise FileNotFoundError(f"Bundled FlowKit not found: {work}")
    logs = PROJECT_ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout = (logs / "flowkit-agent.out.log").open("ab")
    stderr = (logs / "flowkit-agent.err.log").open("ab")
    return subprocess.Popen(
        [sys.executable, "-m", "agent.main"],
        cwd=str(work),
        stdout=stdout,
        stderr=stderr,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def open_chrome_with_extension(url: str | None = None) -> subprocess.Popen:
    cfg = load_config()
    chrome = cfg.get("chrome_path") or shutil.which("chrome") or shutil.which("google-chrome")
    if not chrome:
        raise FileNotFoundError("Chrome not found. Set chrome_path in config.json.")
    profile = Path(cfg.get("chrome_profile_dir") or PROJECT_ROOT / "chrome-profile")
    profile.mkdir(parents=True, exist_ok=True)
    extension = VENDOR_FLOWKIT / "extension"
    url = url or flow_project_url(cfg.get("project_id"))
    args = [
        str(chrome),
        f"--user-data-dir={profile}",
        f"--load-extension={extension}",
        f"--disable-extensions-except={extension}",
        url,
    ]
    return subprocess.Popen(args)
