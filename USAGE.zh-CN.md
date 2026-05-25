# Flow API Tool 中文指南

Flow API Tool 是一个面向 Google Flow / Nano Banana Pro 图片工作流的本地自动化工具。它把网页里反复点击的流程，整理成可以复用、可以写脚本、可以批量生成和下载的命令行工具。

它不是官方 API，也不是托管服务。它运行在你的电脑上，通过本地 Chrome 扩展桥接你自己的 Flow 网页会话，适合个人创作、提示词测试、参考图复用和图片生产流程整理。

## 这个项目解决什么问题

如果你经常用 Flow 生成图片，通常会遇到这些麻烦：

- 每次都要手动上传参考图，重复劳动很多。
- 参考图生成后的 ID 不好管理，下次很难复用。
- 想一次生成多张图、批量测试提示词，网页操作效率低。
- 2K/4K 下载要在网页里点来点去，不适合批量处理。
- 想把生成流程接进自己的 Python 脚本，没有一个顺手的入口。

这个项目的目标就是把这些事情变成稳定的本地工作流：

- 用命令行生成图片。
- 用 `@角色名`、`@产品名` 这样的方式引用参考图。
- 把参考图的本地名称、media id、标签、备注保存到本地数据库。
- 生成后自动下载真实 2K/4K 文件。
- 用 Python API 接入自己的脚本、批处理或内部工具。

## 适合谁用

适合这些场景：

- 设计师或内容创作者：需要反复测试角色、产品、场景提示词。
- AI 图片工作流玩家：需要管理一批可复用的参考图。
- 开发者：想把 Flow 图片生成接入自己的 Python 脚本。
- 小团队：需要把生成结果、提示词、参考图流程整理得更可追踪。

不适合这些场景：

- 想做公开 SaaS API 服务。
- 想绕过平台限制或批量滥用账号。
- 不想自己登录 Flow 网页，只想拿一个纯后端 API key 直接跑。

## 可以直接在 Codex 里使用

这个项目很适合放在 Codex 工作区里直接使用。原因很简单：它不是一个需要复杂后台部署的服务，而是一组本地 PowerShell 脚本、Python 命令和本地状态文件。只要你的本地 Flow 网页会话已经连上，Codex 就可以直接帮你运行、修改和组织整个图片生成流程。

你可以在 Codex 里这样说：

```text
帮我检查 Flow bridge 是否已经连接。
把 refs/character.png 上传成 @character_a，然后生成 4 张 2K 科技风角色图。
用 @product_a 生成 3 组产品海报，并把结果下载到 outputs。
读取最新的 response.json，重新下载 2K 图片。
帮我写一个批处理脚本，把这 10 条提示词都跑一遍。
```

Codex 可以帮你做这些事：

- 修改提示词和批量生成脚本。
- 运行 `flow.py` 上传参考图、生成图片、下载 2K/4K。
- 查看 `outputs/` 里的结果和响应 JSON。
- 帮你整理参考图名称，比如 `@character_a`、`@product_a`、`@scene_ref`。
- 根据你现有的 Python 代码，把 Flow 生成流程接进去。

你的 `config.json`、浏览器 profile、日志、参考图、生成图和本地数据库仍然只保存在本机，不会因为 Codex 操作就自动提交到 GitHub。

## 它算不算 Agent

更准确地说，它是一个 **local agent bridge**。

项目里包含本地 FlowKit agent，它负责协调本地服务、Chrome 扩展、Flow 网页会话、参考图上传、生成任务和高清下载。但它不是那种会自己理解目标、自动规划创作方向的全自动 AI Agent。

简单理解：

```text
你写命令或 Python 代码
        |
        v
Flow API Tool
        |
        v
本地 FlowKit agent
        |
        v
Chrome 扩展桥接你的 Flow 网页会话
        |
        v
Google Flow 生成和下载图片
```

## 安装和初始化

克隆项目：

```powershell
git clone https://github.com/shualai/flow_tool.git
cd flow_tool
```

安装依赖：

```powershell
.\setup.ps1
```

复制配置模板：

```powershell
copy .\config.example.json .\config.json
```

编辑 `config.json`：

```json
{
  "base_url": "http://127.0.0.1:8100",
  "project_id": "你的 Flow 项目 ID",
  "user_paygate_tier": "PAYGATE_TIER_ONE",
  "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
  "chrome_path": "你的 Chrome 路径",
  "chrome_profile_dir": "./chrome-profile"
}
```

`config.json` 是你的本地私有配置，里面可能包含项目 ID 和本地路径，不要提交到 GitHub。

## 启动本地桥接

先启动本地 agent：

```powershell
.\start_agent.ps1
```

再打开带扩展的 Chrome：

```powershell
.\open_flow_chrome.ps1
```

在打开的 Chrome 里登录 Google Flow。登录完成后检查状态：

```powershell
python .\flow.py status
```

看到 `extension_connected` 和 `flow_key_present` 为 true，说明本地桥接已经可用。

## 第一次生成图片

生成一张图，并下载 2K：

```powershell
python .\flow.py generate "cinematic macro futuristic city core, ultra detailed, realistic lighting" --count 1 --download --prefix tech
```

一次生成多张：

```powershell
python .\flow.py generate "premium product campaign, realistic studio lighting, clean background" --count 4 --download --prefix product
```

只保存预览图：

```powershell
python .\flow.py generate "minimal product render on white background" --quality preview
```

下载 4K：

```powershell
python .\flow.py generate "futuristic city skyline, cinematic lighting" --download --quality 4k
```

默认情况下，如果 2K/4K 下载失败，程序不会把预览图伪装成高清图。你明确允许失败后保存预览图时，再加：

```powershell
python .\flow.py generate "product render" --download --fallback-preview
```

## 参考图资产库

参考图复用是这个项目最实用的部分。

上传一张参考图，并保存成一个名字：

```powershell
python .\flow.py upload .\refs\character.png --name character_a --tag role --note "主角参考图"
```

之后你不需要每次重新上传这张图，可以直接在提示词里引用：

```powershell
python .\flow.py generate "@character_a standing on a futuristic rooftop, cinematic lighting" --count 2 --download
```

如果名称里有空格：

```powershell
python .\flow.py generate "@[main character] fashion editorial, studio lighting" --count 2
```

多个参考图一起用：

```powershell
python .\flow.py generate "@character_a @product_a character holding the product, realistic commercial photography" --count 2 --download
```

查看保存过的参考图：

```powershell
python .\flow.py refs
```

按标签筛选：

```powershell
python .\flow.py refs --tag role
```

搜索：

```powershell
python .\flow.py refs --search character
```

删除一个本地映射：

```powershell
python .\flow.py ref-delete character_a
```

删除映射只影响本地数据库，不代表删除 Google Flow 里的远端素材。

## 下载已有结果

如果你之前保存了响应 JSON，可以从响应文件里下载：

```powershell
python .\flow.py download --response-json .\outputs\run\response.json --quality 2k
```

如果你已经知道 media id，可以直接高清下载：

```powershell
python .\flow.py upsample MEDIA_ID --resolution 2k
```

## Python 调用

最小示例：

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

这个入口适合接入你自己的批处理脚本，例如：

- 批量跑不同提示词版本。
- 给同一个角色生成多套场景。
- 给产品图生成不同广告风格。
- 把结果路径写入自己的素材管理表。

## 常用命令速查

```powershell
python .\flow.py status
python .\flow.py credits
python .\flow.py upload .\refs\character.png --name character_a
python .\flow.py refs
python .\flow.py generate "your prompt" --count 4 --download --quality 2k
python .\flow.py download --response-json .\outputs\run\response.json --quality 2k
python .\flow.py upsample MEDIA_ID --resolution 2k
```

## 本地目录说明

这些目录是运行时数据，默认不会提交到 GitHub：

- `config.json`：你的本地配置。
- `chrome-profile/`：本地 Chrome 用户数据。
- `refs/`：你放在本地的参考图文件。
- `state/`：本地数据库、参考图映射和运行状态。
- `outputs/`：生成结果、下载图片和响应 JSON。
- `logs/`：本地 agent 日志。

开源或分享项目时，不要手动压缩整个运行目录。

## 公开发布打包

如果你要发给别人或做公开发布包，使用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\export_portable.ps1 -PublicRelease
```

这个模式会排除私有配置、浏览器状态、日志、生成结果、参考图文件、本地数据库和 FlowKit 运行数据库。

## 安全和合规提醒

- 只使用你有权使用的账号、素材和内容。
- 不要提交 Cookie、browser profile、access token、日志、生成结果、参考图和本地数据库。
- 不要把这个项目包装成 Google 官方 API。
- 不建议直接做成公开多人使用的托管服务。
- 使用前请自行确认 Google Flow、Google Labs、Google 账号和 reCAPTCHA 相关条款。

## 常见问题

### status 显示扩展没有连接

重新运行：

```powershell
.\open_flow_chrome.ps1
```

确认打开的 Chrome 已经进入 Flow 页面，并且账号已登录。

### 生成时报 reCAPTCHA 或 unusual activity

先暂停请求，不要连续重试。重新登录 Flow，降低生成频率。如果还是失败，换网络或等待一段时间再试。

### 2K/4K 下载失败

先确认你的 Flow 网页端账号本身支持高清下载。不同账号和地区可能能力不同。

### 参考图是不是每次都要上传

不用。上传成功后，本地会保存名称和 media id 的映射。下次直接用 `@name` 引用即可。

### 可以跨电脑复用参考图吗

可以，但需要迁移本地参考图数据库或重新上传参考图。公开仓库默认不会包含你的 `state/` 和 `refs/`，这是为了防止泄露私有素材。

## 给开源用户的一句话

如果你需要的是一个本地、可脚本化、能管理参考图、能下载高清结果的 Flow 图片工作流工具，这个项目就是为这个场景做的。

如果它帮你少点了很多网页按钮，欢迎给仓库点一个 Star，让更多需要这种工作流的人找到它。
