# Flow API Tool

Local command-line and Python wrapper for working with Google Flow through a Chrome extension bridge.

This project is intended for personal/local automation with your own browser session. It is not an official Google product.

Chinese usage guide: [USAGE.zh-CN.md](USAGE.zh-CN.md)

## Important Notice

- Use this only with accounts and content you are authorized to use.
- Review and follow Google Flow, Google Labs, Google account, and reCAPTCHA terms before using or publishing this project.
- Do not commit cookies, browser profiles, access tokens, generated private media, uploaded references, logs, or local databases.
- This repository vendors FlowKit, which is MIT licensed. Keep its license and attribution if you redistribute it.

## What It Does

- Starts a local FlowKit agent.
- Opens Chrome with the bundled extension.
- Uploads reusable reference images and stores local name-to-media-id mappings.
- Generates images through Flow.
- Downloads real Flow 2K/4K upsampled images when the account supports it.

## Project Layout

- `flow.py`: CLI entrypoint.
- `src/flow_api.py`: Python wrapper.
- `src/ref_store.py`: local SQLite reference library.
- `vendor/flowkit`: bundled FlowKit.
- `config.example.json`: safe public config template.
- `export_portable.ps1`: creates a clean portable zip.

Runtime-only folders are ignored by git:

- `chrome-profile/`
- `logs/`
- `outputs/`
- `refs/`
- `state/`

## Setup

```powershell
cd path\to\flow_api_tool
.\setup.ps1
copy .\config.example.json .\config.json
```

Edit `config.json`:

```json
{
  "base_url": "http://127.0.0.1:8100",
  "project_id": "YOUR_FLOW_PROJECT_ID",
  "user_paygate_tier": "PAYGATE_TIER_ONE",
  "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
  "chrome_path": "C:/Path/To/Chrome/Application/chrome.exe",
  "chrome_profile_dir": "./chrome-profile"
}
```

Start the local bridge:

```powershell
.\start_agent.ps1
.\open_flow_chrome.ps1
python .\flow.py status
```

When `extension_connected` and `flow_key_present` are true, the local bridge is ready.

## Generate Images

```powershell
python .\flow.py generate "cinematic macro futuristic city core, ultra detailed, technology style" --count 1 --download --prefix tech
```

Default download quality is `2k` and uses Flow's `upsampleImage` endpoint. To save only the preview image:

```powershell
python .\flow.py generate "product render on white background" --quality preview
```

If high-resolution download fails, the command does not silently save the preview as if it were 2K. To allow preview fallback:

```powershell
python .\flow.py generate "product render" --fallback-preview
```

## Download Existing Results

From a saved response:

```powershell
python .\flow.py download --response-json .\outputs\run\response.json --quality 2k
```

From a media id:

```powershell
python .\flow.py upsample MEDIA_ID --resolution 2k
```

## Reference Library

Upload a reference image once:

```powershell
python .\flow.py upload .\refs\character.png --name character_a --tag role --note "main character reference"
```

List or search saved references:

```powershell
python .\flow.py refs
python .\flow.py refs character_a
python .\flow.py refs --tag role
python .\flow.py refs --search character
```

Use a saved reference:

```powershell
python .\flow.py generate "@character_a standing on a futuristic rooftop, cinematic lighting" --count 2 --download
```

Names with spaces:

```powershell
python .\flow.py generate "@[main character] cyberpunk portrait" --count 2
```

Multiple references:

```powershell
python .\flow.py generate "@character_a @character_b two characters in the same scene" --count 2
```

Delete a local mapping:

```powershell
python .\flow.py ref-delete character_a
```

## Python API

```python
from src.flow_api import FlowApi

api = FlowApi()
result = api.generate_images(
    "@character_a cinematic technology poster",
    count=2,
    aspect_ratio="landscape",
)

downloaded = api.download_media_response(result, prefix="tech-scene", quality="2k")
for item in downloaded:
    print(item.path, item.width, item.height, item.source)
```

## Portable Export

Use the export script instead of zipping the running directory manually:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\export_portable.ps1
```

Include generated outputs only when needed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\export_portable.ps1 -IncludeOutputs
```

The portable export excludes locked/runtime files such as logs, Chrome profile, and FlowKit runtime databases.
