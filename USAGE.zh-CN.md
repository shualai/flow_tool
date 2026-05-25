# Flow API Tool 中文使用说明

这是一个本地使用的 Google Flow 辅助工具。它通过本机 Chrome 扩展桥接你自己的 Flow 网页会话，用命令行或 Python 代码完成参考图上传、图片生成和 2K/4K 下载。

注意：本项目不是 Google 官方产品。请只在你有权使用的账号、素材和内容范围内使用，并遵守 Google Flow、Google Labs、Google 账号及 reCAPTCHA 相关条款。

## 1. 安装

进入项目目录：

```powershell
cd D:\word\flow_api_tool
```

安装依赖：

```powershell
.\setup.ps1
```

复制配置模板：

```powershell
copy .\config.example.json .\config.json
```

然后编辑 `config.json`：

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

`config.json` 是你的本地私有配置，不要提交到 GitHub。

## 2. 启动本地桥接

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

看到 `extension_connected` 和 `flow_key_present` 为 true，说明可以调用。

## 3. 生成图片

生成一张图并下载 2K：

```powershell
python .\flow.py generate "宏观未来科技城市核心，电影级灯光，超清细节" --count 1 --download --prefix tech
```

一次生成多张：

```powershell
python .\flow.py generate "一个科技感很强的产品海报，白色背景，真实摄影风格" --count 4 --download --prefix product
```

只保存预览图：

```powershell
python .\flow.py generate "一张极简产品图" --quality preview
```

默认高质量下载会调用 Flow 的高清下载能力。如果高清下载失败，程序不会把预览图伪装成 2K。需要允许失败后退回预览图时再加：

```powershell
python .\flow.py generate "一张极简产品图" --download --fallback-preview
```

## 4. 参考图复用

上传一张参考图并命名：

```powershell
python .\flow.py upload .\refs\character.png --name character_a --tag role --note "主角参考图"
```

查看已保存参考图：

```powershell
python .\flow.py refs
```

搜索参考图：

```powershell
python .\flow.py refs --search character
```

在提示词里引用参考图：

```powershell
python .\flow.py generate "@character_a 站在未来城市楼顶，电影感，真实光影" --count 2 --download
```

如果参考图名称带空格：

```powershell
python .\flow.py generate "@[main character] 未来科技风角色海报" --count 2
```

多个参考图一起用：

```powershell
python .\flow.py generate "@character_a @product_a 角色拿着产品，商业摄影风格" --count 2 --download
```

删除本地参考图映射：

```powershell
python .\flow.py ref-delete character_a
```

## 5. 下载已有结果

从响应 JSON 下载：

```powershell
python .\flow.py download --response-json .\outputs\run\response.json --quality 2k
```

从 media id 下载：

```powershell
python .\flow.py upsample MEDIA_ID --resolution 2k
```

## 6. Python 调用示例

```python
from src.flow_api import FlowApi

api = FlowApi()

result = api.generate_images(
    "@character_a 科技风商业海报，真实摄影，电影级布光",
    count=2,
    aspect_ratio="landscape",
)

downloaded = api.download_media_response(result, prefix="tech-scene", quality="2k")
for item in downloaded:
    print(item.path, item.width, item.height, item.source)
```

## 7. 公开发布打包

如果你要发给别人或上传公开仓库，不要手动压缩整个运行目录。使用公开发布模式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\export_portable.ps1 -PublicRelease
```

这个模式会排除：

- `config.json`
- `chrome-profile/`
- `logs/`
- `outputs/` 里的生成结果
- `refs/` 里的本地参考图
- `state/` 里的数据库和运行状态
- FlowKit 运行数据库

## 8. 常见问题

如果 `status` 显示扩展未连接，重新运行 `open_flow_chrome.ps1`，并确认 Chrome 里已经打开 Flow 页面。

如果生成时报 reCAPTCHA 或异常活动，先暂停请求，重新登录 Flow，降低并发和请求频率。

如果 2K 下载失败，先确认网页端账号本身是否支持高清下载。
