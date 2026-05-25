# Flow API Tool

[![GitHub stars](https://img.shields.io/github/stars/shualai/flow_tool?style=social)](https://github.com/shualai/flow_tool/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](requirements.txt)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](USAGE.zh-CN.md)

Local Google Flow / Nano Banana Pro automation toolkit with a CLI, Python SDK, reference-image library, and real 2K/4K download workflow.

> Unofficial local tool for personal Flow workflows. It runs on your own machine, with your own browser session. It is not a Google product.

[中文使用说明](USAGE.zh-CN.md) · [Security](SECURITY.md) · [Open-source checklist](OPEN_SOURCE_CHECKLIST.md)

## Why This Exists

Google Flow is powerful for image workflows, especially when you want reusable references, multiple generations, and high-resolution downloads. The web UI is not always ideal when you are producing many images, testing prompt variants, or managing reference assets across sessions.

Flow API Tool wraps that workflow into a repeatable local tool:

- Generate images from the command line.
- Use saved reference images with `@name` syntax.
- Download real Flow 2K/4K upsampled files when your account supports it.
- Reuse reference media IDs from a local SQLite library.
- Call the same workflow from Python scripts.
- Run the workflow directly inside a Codex workspace.
- Keep runtime secrets, browser state, outputs, and reference files out of git.

## What You Can Build With It

- Batch prompt testing for Nano Banana Pro / Google Flow image workflows.
- Character or product reference libraries that can be reused by name.
- Local image generation pipelines driven by Python.
- Repeatable 2K download workflows instead of manual browser clicking.
- Codex-assisted prompt iteration, reference upload, generation, and result inspection.
- Creative tooling around prompt templates, shot lists, and visual iteration.

## Use It Directly in Codex

This repo is designed to work well inside Codex. Because the tool is just local files, PowerShell scripts, and Python commands, Codex can operate it directly in the workspace after your local Flow browser session is connected.

You can ask Codex to do things like:

```text
Set up this project and check whether the Flow bridge is connected.
Upload refs/character.png as @character_a, then generate 4 cinematic 2K images.
Generate three product poster variants and save the response JSON.
Use the latest response.json in outputs/ and redownload the result as 2K.
Create a Python batch script that tests these 10 prompts with @product_a.
```

Codex can edit prompts, write batch scripts, run `flow.py`, inspect `outputs/`, and help organize reusable reference names while your private config, browser profile, logs, reference images, and generated files stay local.

## Quick Demo

Generate and download a 2K image:

```powershell
python .\flow.py generate "cinematic macro futuristic city core, ultra detailed, realistic lighting" --count 1 --download --prefix tech
```

Upload a reusable reference:

```powershell
python .\flow.py upload .\refs\character.png --name character_a --tag role --note "main character"
```

Use that reference later:

```powershell
python .\flow.py generate "@character_a standing on a futuristic rooftop, cinematic lighting" --count 2 --download
```

Use multiple references:

```powershell
python .\flow.py generate "@character_a @product_a premium product campaign, realistic studio lighting" --count 4 --download
```

Python usage:

```python
from src.flow_api import FlowApi

api = FlowApi()

result = api.generate_images(
    "@character_a cinematic technology poster, realistic lighting",
    count=2,
    aspect_ratio="landscape",
)

downloaded = api.download_media_response(result, prefix="tech-scene", quality="2k")
for item in downloaded:
    print(item.path, item.width, item.height, item.source)
```

## Is This an Agent?

It is best described as a **local agent bridge**, not a fully autonomous AI agent.

The bundled FlowKit agent runs locally and coordinates the browser extension, Flow requests, reference uploads, generation jobs, and downloads. The tool does not independently plan creative tasks like a general-purpose AI agent; it gives you programmable control over your own Google Flow session.

## Architecture

```text
CLI / Python SDK
      |
      v
Local Flow API wrapper
      |
      v
Bundled FlowKit local agent
      |
      v
Chrome extension bridge
      |
      v
Google Flow web session
```

Runtime data stays local:

- `config.json`: your private project and local paths.
- `chrome-profile/`: local Chrome profile.
- `refs/`: local reference image files.
- `state/`: local SQLite reference library and run state.
- `outputs/`: generated files and response JSON.
- `logs/`: local agent logs.

These paths are ignored by git.

## Setup

```powershell
git clone https://github.com/shualai/flow_tool.git
cd flow_tool
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

Start the bridge:

```powershell
.\start_agent.ps1
.\open_flow_chrome.ps1
python .\flow.py status
```

When `extension_connected` and `flow_key_present` are true, the local bridge is ready.

## CLI Commands

```powershell
python .\flow.py status
python .\flow.py credits
python .\flow.py upload .\refs\character.png --name character_a
python .\flow.py refs
python .\flow.py generate "your prompt" --count 4 --download --quality 2k
python .\flow.py download --response-json .\outputs\run\response.json --quality 2k
python .\flow.py upsample MEDIA_ID --resolution 2k
```

Generation options:

```powershell
python .\flow.py generate "product render on white background" --quality preview
python .\flow.py generate "product render" --download --quality 4k
python .\flow.py generate "product render" --download --fallback-preview
```

The default high-resolution path uses Flow's upsample workflow. If 2K/4K download fails, the tool does not silently save a preview image as if it were high resolution unless `--fallback-preview` is set.

## Reference Image Library

Save once:

```powershell
python .\flow.py upload .\refs\character.png --name character_a --tag role --note "main character reference"
```

Find later:

```powershell
python .\flow.py refs
python .\flow.py refs --tag role
python .\flow.py refs --search character
```

Prompt with references:

```powershell
python .\flow.py generate "@character_a cyberpunk portrait, neon city, realistic lighting" --count 2
python .\flow.py generate "@[main character] fashion editorial, studio lighting" --count 2
```

Delete a local mapping:

```powershell
python .\flow.py ref-delete character_a
```

## Project Layout

```text
flow.py                 CLI entrypoint
src/flow_api.py         Python wrapper
src/ref_store.py        Local SQLite reference library
vendor/flowkit          Bundled FlowKit agent and extension
config.example.json     Public config template
export_portable.ps1     Clean export script
USAGE.zh-CN.md          Chinese usage guide
```

## Portable Export

Use the export script instead of manually zipping a running directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\export_portable.ps1 -PublicRelease
```

The public release export excludes private config, browser profile, logs, outputs, local reference images, local state, and FlowKit runtime databases.

## Important Notice

- Use this only with accounts and content you are authorized to use.
- Review and follow Google Flow, Google Labs, Google account, and reCAPTCHA terms before using or publishing this project.
- Do not commit cookies, browser profiles, access tokens, generated private media, uploaded references, logs, or local databases.
- This repository vendors FlowKit, which is MIT licensed. Keep its license and attribution if you redistribute it.

## Star This Project

If this saves you from manually uploading references, clicking download buttons, or rebuilding Flow workflows by hand, a star helps more people find it.
