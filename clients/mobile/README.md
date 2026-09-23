# AgentDock Mobile (Flutter)

正式手机瘦客户端：原生麦克风 + `ws://主机:8765`。  
**不包含** Runtime / STT / TTS / Agent。

## 本机开发

需安装 [Flutter](https://docs.flutter.dev/get-started/install) **≥ 3.27**（`record` / Android 插件依赖 `flutter.compileSdkVersion`）。

```bash
cd clients/mobile
flutter create . --project-name agentdock_mobile --org com.agentdock --platforms=android,ios,windows,macos
# 首次生成平台目录后，确认麦克风权限（见下方）；Android compileSdk/targetSdk 建议 35
flutter pub get
# 用 brand/app-icon.png 覆盖已创建平台的默认启动图标（CI 同一步骤）
bash tool/apply_brand_icons.sh
flutter run
```

品牌启动图源：`clients/mobile/brand/app-icon.png`（由 `python scripts/generate_brand_icons.py` 从 `assets/brand` 同步）。
`tool/apply_brand_icons.sh` 只对已存在的 `android` / `ios` / `windows` / `macos` 目录生成图标；GitHub Actions `Build Clients` 在 `flutter create` + `pub get` 之后会跑该脚本。

交互与 Web 一致：

- **点按角色**：开始 / 结束录音
- **长按角色**：打开设置（仅 Runtime URL / Token；TTS/人物由主机下发）
- **下方三行回复**：按句字幕；空闲时可点回复重播

## Android 权限

`android/app/src/main/AndroidManifest.xml` 需有：

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.RECORD_AUDIO"/>
```

CI 会在 `flutter create` 后自动补上。

## 打包（GitHub Actions）

工作流：[`.github/workflows/build-clients.yml`](../../.github/workflows/build-clients.yml)

| Artifact | 说明 |
|----------|------|
| `agentdock-android` | Release APK |
| `agentdock-windows` | Windows Release 目录 zip |
| `agentdock-macos` | `.app` zip（未公证） |
| `agentdock-ios-unsigned` | 未签名 IPA，给 **巨魔 / 侧载**（非 App Store） |

```bash
flutter build apk --release
flutter build windows --release
flutter build macos --release
flutter build ios --release --no-codesign   # 再打成 Payload/*.ipa
```

## 目录

```text
lib/
  protocol/   # Device Protocol 编解码
  session/    # WS + 状态机
  audio/      # 录音 WAV / 播 TTS
  ui/         # 点按通话 UI
```
