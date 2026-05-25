from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


API_HOST = os.environ.get("FLOW_TOOL_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("FLOW_TOOL_API_PORT", "8100"))
GOOGLE_FLOW_API = "https://aisandbox-pa.googleapis.com"
GOOGLE_API_KEY = os.environ.get("GOOGLE_FLOW_API_KEY", "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY")


def normalize_image_model(value: str | None) -> str:
    if not value:
        return "NARWHAL"
    key = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "nanobanana": "NARWHAL",
        "nanobanana2": "NARWHAL",
        "narwhal": "NARWHAL",
        "nanobananapro": "GEM_PIX_2",
        "gempix2": "GEM_PIX_2",
    }
    return aliases.get(key, value.strip())


DEFAULT_IMAGE_MODEL_NAME = normalize_image_model(os.environ.get("FLOW_IMAGE_MODEL", "nanobanana"))

ENDPOINTS = {
    "generate_images": "/v1/projects/{project_id}/flowMedia:batchGenerateImages",
    "upscale_image": "/v1/flow/upsampleImage",
    "upload_image": "/v1/flow/uploadImage",
    "get_credits": "/v1/credits",
    "get_media": "/v1/media/{media_id}",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("flow_tool.bridge")


def browser_headers() -> dict[str, str]:
    return {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "text/plain;charset=UTF-8",
        "origin": "https://labs.google",
        "referer": "https://labs.google/",
    }


def build_url(endpoint_key: str, **kwargs: str) -> str:
    path = ENDPOINTS[endpoint_key].format(**kwargs)
    sep = "&" if "?" in path else "?"
    return f"{GOOGLE_FLOW_API}{path}{sep}key={GOOGLE_API_KEY}"


def client_context(project_id: str, user_paygate_tier: str = "PAYGATE_TIER_ONE") -> dict[str, Any]:
    return {
        "projectId": str(project_id),
        "recaptchaContext": {
            "applicationType": "RECAPTCHA_APPLICATION_TYPE_WEB",
            "token": "",
        },
        "sessionId": f";{int(time.time() * 1000)}",
        "tool": "PINHOLE",
        "userPaygateTier": user_paygate_tier,
    }


class ExtensionBridge:
    def __init__(self) -> None:
        self.websocket: WebSocket | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.flow_key: str | None = None
        self.connect_count = 0
        self.disconnect_count = 0
        self.connected_at: float | None = None
        self.callback_secret = secrets.token_urlsafe(32)

    @property
    def connected(self) -> bool:
        return self.websocket is not None

    @property
    def stats(self) -> dict[str, Any]:
        uptime = int(time.time() - self.connected_at) if self.connected and self.connected_at else None
        return {
            "connected": self.connected,
            "connects": self.connect_count,
            "disconnects": self.disconnect_count,
            "uptime_s": uptime,
        }

    async def attach(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.connect_count += 1
        self.connected_at = time.time()
        logger.info("Extension connected")
        await websocket.send_text(json.dumps({"type": "callback_secret", "secret": self.callback_secret}))

    def detach(self) -> None:
        self.websocket = None
        self.disconnect_count += 1
        self.connected_at = None
        for future in list(self.pending.values()):
            if not future.done():
                future.set_exception(ConnectionError("Extension disconnected"))
        self.pending.clear()
        logger.info("Extension disconnected")

    async def handle_message(self, data: dict[str, Any]) -> None:
        msg_type = data.get("type")
        if msg_type == "token_captured":
            self.flow_key = data.get("flowKey") or self.flow_key
            logger.info("Flow token captured by extension")
            return
        if msg_type == "extension_ready":
            logger.info("Extension ready, flowKey=%s", "yes" if data.get("flowKeyPresent") else "no")
            return
        if msg_type == "ping":
            if self.websocket:
                await self.websocket.send_text(json.dumps({"type": "pong"}))
            return
        if msg_type in {"pong", "media_urls_refresh"}:
            return

        req_id = data.get("id")
        if req_id and req_id in self.pending:
            future = self.pending[req_id]
            if not future.done():
                future.set_result(data)

    async def send(self, method: str, params: dict[str, Any], timeout: float = 300) -> dict[str, Any]:
        if not self.websocket:
            return {"error": "Extension not connected"}

        req_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = future
        try:
            await self.websocket.send_text(json.dumps({"id": req_id, "method": method, "params": params}))
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"error": f"Timeout waiting for {method}"}
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            self.pending.pop(req_id, None)


bridge = ExtensionBridge()
app = FastAPI(title="Flow Tool Local Bridge", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class GenerateImageRequest(BaseModel):
    prompt: str
    project_id: str
    aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"
    character_media_ids: list[str] | None = None
    image_model: str | None = None
    count: int = 1


class UploadImageRequest(BaseModel):
    file_path: str
    project_id: str = ""
    file_name: str = "image.png"


class UpsampleImageRequest(BaseModel):
    media_id: str
    project_id: str = ""
    target_resolution: str = "UPSAMPLE_IMAGE_RESOLUTION_2K"
    user_paygate_tier: str = "PAYGATE_TIER_ONE"


def unwrap_or_raise(result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status", 200)
    if result.get("error"):
        raise HTTPException(status if isinstance(status, int) and status >= 400 else 502, result["error"])
    if isinstance(status, int) and status >= 400:
        raise HTTPException(status, result.get("data", "Flow request failed"))
    data = result.get("data", result)
    return data if isinstance(data, dict) else {"data": data}


@app.websocket("/ws")
async def extension_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    await bridge.attach(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                await bridge.handle_message(json.loads(raw))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from extension")
    except WebSocketDisconnect:
        bridge.detach()


@app.post("/api/ext/callback")
async def extension_callback(request: Request) -> dict[str, Any]:
    data = await request.json()
    req_id = data.get("id")
    if req_id and req_id in bridge.pending:
        future = bridge.pending[req_id]
        if not future.done():
            future.set_result(data)
        return {"ok": True}
    return {"ok": False, "reason": "no matching pending request"}


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": "0.1.0",
        "extension_connected": bridge.connected,
        "ws": bridge.stats,
    }


@app.get("/api/flow/status")
async def flow_status() -> dict[str, Any]:
    return {
        "connected": bridge.connected,
        "flow_key_present": bridge.flow_key is not None,
    }


@app.get("/api/flow/credits")
async def credits() -> dict[str, Any]:
    result = await bridge.send(
        "api_request",
        {
            "url": build_url("get_credits"),
            "method": "GET",
            "headers": browser_headers(),
        },
        timeout=30,
    )
    return unwrap_or_raise(result)


@app.post("/api/flow/upload-image")
async def upload_image(body: UploadImageRequest) -> dict[str, Any]:
    path = Path(body.file_path).expanduser().resolve()
    if not path.exists():
        raise HTTPException(404, f"File not found: {path}")

    image_base64 = base64.b64encode(path.read_bytes()).decode()
    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    result = await bridge.send(
        "api_request",
        {
            "url": build_url("upload_image"),
            "method": "POST",
            "headers": browser_headers(),
            "body": {
                "clientContext": {
                    "projectId": body.project_id,
                    "tool": "PINHOLE",
                },
                "fileName": body.file_name,
                "imageBytes": image_base64,
                "isHidden": False,
                "isUserUploaded": True,
                "mimeType": mime_type,
            },
        },
        timeout=60,
    )
    data = unwrap_or_raise(result)
    media = data.get("media") if isinstance(data, dict) else None
    media_id = media.get("name") if isinstance(media, dict) else None
    return {"media_id": media_id, "raw": data}


@app.post("/api/flow/generate-image")
async def generate_image(body: GenerateImageRequest) -> dict[str, Any]:
    ts = int(time.time() * 1000)
    ctx = client_context(body.project_id, body.user_paygate_tier)
    count = max(1, min(int(body.count or 1), 8))
    image_model_name = normalize_image_model(body.image_model or DEFAULT_IMAGE_MODEL_NAME)
    requests = []
    for index in range(count):
        item = {
            "clientContext": {**ctx, "sessionId": f";{ts + index}"},
            "seed": (ts + index) % 1000000,
            "structuredPrompt": {"parts": [{"text": body.prompt}]},
            "imageAspectRatio": body.aspect_ratio,
            "imageModelName": image_model_name,
        }
        if body.character_media_ids:
            item["imageInputs"] = [
                {"name": media_id, "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"}
                for media_id in body.character_media_ids
            ]
        requests.append(item)

    payload: dict[str, Any] = {"clientContext": ctx, "requests": requests}
    if body.character_media_ids or count > 1:
        payload["mediaGenerationContext"] = {"batchId": str(uuid.uuid4())}
        payload["useNewMedia"] = True

    result = await bridge.send(
        "api_request",
        {
            "url": build_url("generate_images", project_id=body.project_id),
            "method": "POST",
            "headers": browser_headers(),
            "body": payload,
            "captchaAction": "IMAGE_GENERATION",
        },
        timeout=300,
    )
    return unwrap_or_raise(result)


@app.post("/api/flow/upsample-image")
async def upsample_image(body: UpsampleImageRequest) -> dict[str, Any]:
    ctx = client_context(body.project_id, body.user_paygate_tier)
    ctx["recaptchaToken"] = ""
    result = await bridge.send(
        "api_request",
        {
            "url": f"{GOOGLE_FLOW_API}{ENDPOINTS['upscale_image']}",
            "method": "POST",
            "headers": {},
            "body": {
                "clientContext": ctx,
                "mediaId": body.media_id,
                "targetResolution": body.target_resolution,
            },
            "captchaAction": "IMAGE_GENERATION",
        },
        timeout=300,
    )
    return unwrap_or_raise(result)


@app.get("/api/flow/media/{media_id}")
async def get_media(media_id: str) -> dict[str, Any]:
    result = await bridge.send(
        "api_request",
        {
            "url": build_url("get_media", media_id=media_id) + "&clientContext.tool=PINHOLE",
            "method": "GET",
            "headers": browser_headers(),
        },
        timeout=30,
    )
    return unwrap_or_raise(result)


def main() -> None:
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")


if __name__ == "__main__":
    main()
