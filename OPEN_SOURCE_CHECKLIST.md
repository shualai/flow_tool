# Open Source Checklist

Use this before publishing the repository.

## Must Not Publish

- `config.json`
- `.env` or other local environment files
- `chrome-profile/`
- `logs/`
- `outputs/`
- `refs/`
- `state/`
- `vendor/flowkit/flow_agent.db*`
- portable zip files such as `flow_api_tool_portable.zip`
- screenshots or generated files that contain private project, account, or client data

## Replace Before Publishing

- Remove local paths such as `D:\...` or `C:\Users\...` from docs and examples.
- Remove real Flow project IDs from docs and config templates.
- Do not publish Google account emails, cookies, Bearer tokens, or generated reference IDs tied to private work.
- Keep `config.example.json` generic and empty where possible.

## Legal And Terms

- This is an unofficial local automation wrapper. Say that clearly.
- Ask users to comply with Google Flow, Google Labs, Google account, and reCAPTCHA terms.
- Do not present this as a way to bypass official access, quotas, paid features, or safety systems.
- Do not run this as a public hosted service for other users' accounts unless you have reviewed the legal and platform requirements.
- Keep the vendored FlowKit MIT license and attribution.

## Suggested Repository Files

- `README.md`
- `LICENSE`
- `SECURITY.md`
- `config.example.json`
- `.gitignore`
- source code and scripts only

## Pre-Publish Commands

```powershell
python -m py_compile .\flow.py .\src\flow_api.py .\src\ref_store.py
rg -n "ya29\.|Bearer|access_token|refresh_token|Cookie|agt_codex|D:\\|C:\\Users|@gmail|@.*\.com|0d64d5f3" -S . --glob "!vendor/**" --glob "!state/**" --glob "!outputs/**" --glob "!logs/**"
```

The second command should return no private values from your own project files.
