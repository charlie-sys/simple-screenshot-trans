# 轻译 · Float Translate

适用于 Windows 10 / 11 的轻量悬浮翻译工具。Python + Tk 原生窗口，运行时无第三方 Python 依赖，无 Electron、浏览器内核或本地 OCR 模型。

## 运行

双击 `dist/FloatTranslate.exe`，无需安装 Python。源码运行需要带 Tk 的 Python 3.9 或更高版本：

```powershell
python main.py
```

也可以双击 `start.vbs` 无控制台启动源码版（需要 `pythonw.exe` 在 PATH 中）。

## 首次配置

点击「设置」，填写：

- **接口地址**：例如 `https://你的服务/v1` 或完整的 `https://你的服务/v1/chat/completions`。本机服务可用 `http://127.0.0.1:端口/v1`。
- **模型名称**：服务商提供的准确模型 ID。截图翻译要求该模型以及服务端支持图片输入。
- **API Key**：按服务商要求填写。本地无鉴权服务可留空。

当前支持 OpenAI 兼容的 **Chat Completions** 协议，不直接支持 Anthropic Messages、原生 Gemini 协议或仅支持 Responses 的模型。可以通过兼容网关连接其他服务。图片采用 PNG Base64 `image_url` 输入，格式参考 [OpenAI 官方视觉文档](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)。无内置付费账号，无需绑定特定厂商；翻译费用由所配置的服务商收取。

## 使用

- **文字翻译**：选择源语言和目标语言，输入或粘贴文字，点击翻译，或按 `Ctrl+Enter`。
- **截图翻译**：点击「框选截图」，拖动选择矩形区域，松开鼠标自动翻译。选区阶段可按 `Esc` 或右键取消。支持虚拟桌面和多显示器，包括主屏左侧的副屏。
- **语言选择**：源语言可自动识别，也可明确指定。两端均允许直接输入其他语言名称；「⇄」交换指定语言。
- **悬浮条**：点击「−」折叠；点击「□」展开。拖动标题区域移动窗口；展开时拖动右下角改变大小。点击「×」退出。
- **全局快捷键**：`Ctrl+Alt+A` 框选截图；`Ctrl+Alt+T` 展开窗口。快捷键冲突会在底部提示，按钮仍可使用。
- **重试截图**：截图保留在当前进程内存，点击翻译可再次翻译。输入文字后优先翻译文字；清空文字可重新翻译此前截图。「清空」删除当前截图和文字。
- **取消等待**：翻译期间按 `Esc`，过期结果不会覆盖新的译文。服务端仍可能继续处理并计费。

## 配置与隐私

配置保存在 `%APPDATA%/FloatTranslate/config.json`，API Key 使用 Windows DPAPI 加密，与当前 Windows 用户绑定。截图不写入磁盘，不记录翻译历史。点击翻译、或松开截图选区后，相关内容将发送至你配置的接口。远程接口强制使用 HTTPS；HTTP 仅允许本机地址。程序不收集遥测。

## 开发与打包

```powershell
python -m unittest discover -s tests -v
python -m pip install pyinstaller
.\build.ps1
```

输出为 `dist/FloatTranslate.exe`。打包依赖 PyInstaller，运行程序本身无第三方 Python 依赖。未签名 EXE 可能显示 Windows 发布者提示。

自动测试覆盖实际 GDI 截图、PNG 像素编码、DPAPI 密钥往返、本机模拟 HTTP 服务的文字/图片请求、错误处理、地址校验、窗口折叠展开、设置按钮可见性、选区取消和过期结果隔离。真实云端接口需要配置用户凭据后验证；识别效果和延迟取决于模型与服务。
