# openWakeWord 自训（AgentDock Pi）

在 **PC / Colab** 上训，把 `.onnx` 拷到树莓派；Zero 2 W 上不训。

## 最快：Google Colab

1. 打开：https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing  
   （官方 notebook 挂了就用：https://github.com/alfiedennen/openwakeword-colab-2026）
2. 把目标短语改成你的词（见下方 `phrase.txt`）
3. 全部跑完，下载 `*.onnx`
4. 拷到树莓派，例如：`models/hey_xiaoai.onnx`（短语：hey 小哀）
5. 改 `clients/rpi/config.yaml`：

```yaml
listen:
  mode: wake
  model: "models/hey_xiaoai.onnx"
  threshold: 0.5
```

## 本机（可选）

官方自动配置见同目录 `custom_model.yml`。完整依赖多（Piper、RIR、负样本特征等），细节：

- https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb
- 示例配置：https://github.com/dscripka/openWakeWord/blob/main/examples/custom_model.yml

建议优先 Colab；本机环境容易因依赖版本卡住。

## 用自己的声音重训（推荐）

合成音只是占位；要好控，请在**真实麦克风 + 真实房间**录。本机助手脚本：

```powershell
cd clients\rpi\wakeword

.\record.ps1 archive-tts   # 先把 Edge-TTS 旧样本挪走（可选）
.\record.ps1 pos           # 50 条「hey 小哀」——Enter 后勿碰键盘
.\record.ps1 neg-speech    # 说话 + 近音（嘿小爱、小爱同学…）勿说完整唤醒词
.\record.ps1 neg-silence
.\record.ps1 neg-keyboard  # 可选但很有用
.\record.ps1 neg-tv        # 可选
.\record.ps1 train         # 重训并拷到 clients/rpi/models/hey_xiaoai.onnx
.\record.ps1 test          # 本机开麦试命中（Ctrl+C 结束）
```

录正样本时：提示 `>>> NOW <<<` 再说，刻意变化音量/语速/距离。负样本里**永远不要**说完整的「hey 小哀」。

本机试唤醒也可直接：

```powershell
cd clients\rpi\wakeword
.\record.ps1 test
# 或:  ..\..\..\VoiceForge\.venv\Scripts\python.exe test_wake.py --threshold 0.5
#      python test_wake.py --list-devices
```

## 短语建议

- 当前默认：`hey 小哀` → 模型 `clients/rpi/models/hey_xiaoai.onnx`
- 越短越好（2～4 音节），太长难训、延迟大

先编辑本目录 `phrase.txt`，再 Colab 或本机 `record.ps1` / `train_workspace`。
