# Raspberry Pi voice terminal

树莓派只当嘴和耳：常开唤醒、录音、静音结束、WebSocket 把 WAV 送给电脑上的 Runtime（STT / Agent / TTS），再播回来。

```bash
cd clients/rpi
pip install -r requirements.txt
python -m device
```

配置：`config.yaml` → `runtime_url`（电脑 IP / Tailscale，不要用树莓派自己的 `127.0.0.1`）、麦克风、唤醒词。

## 默认：唤醒词

1. 待命时麦克风常开，唤醒前的数据**丢弃**
2. [openWakeWord](https://github.com/dscripka/openWakeWord) 命中后开始缓冲
3. [webrtcvad](https://github.com/wiseman/py-webrtcvad) 连续静音（默认 1.5s）结束录音
4. 发给 Runtime，播放回传 TTS

默认唤醒词：**hey 小哀**（`listen.model: models/hey_xiaoai.onnx`）。也可改用内置英文 `hey_jarvis` / `alexa` / `hey_mycroft`，或其它自训 `.onnx` / `.tflite` 路径。

首次运行会下载 openWakeWord 模型，Pi 需要能上网。

`listen.mode: button` 可回到旧交互：**第一次按键/Enter 开始，第二次结束**。

## 麦克风

`audio.device` 填 sounddevice 序号或 ALSA 名（如 `plughw:1,0`）。`null` 用系统默认。

## OLED 中文（豆腐块）

屏上中文变方块 = 系统没有可用 CJK 字体。在派上装一个即可：

```bash
sudo apt install -y fonts-wqy-microhei
# 或: sudo apt install -y fonts-noto-cjk
```

然后重启 `python -m device`。日志应出现 `OLED CJK font: ...`。也可在 `config.yaml` 里设 `display.font: /path/to/xxx.ttf`。

## 蓝牙播放

TTS 回传默认走系统默认输出。要接蓝牙耳机/音箱，先在 Pi 上装好蓝牙音频，再（可选）用 `audio.playback_device` 指定输出。

```bash
# Raspberry Pi OS Bookworm（PipeWire）
sudo apt install -y bluez pipewire-pulse libspa-0.2-bluetooth

# 旧版 Bullseye（PulseAudio）
# sudo apt install -y bluez pulseaudio pulseaudio-module-bluetooth
```

配对并连接：

```bash
bluetoothctl
power on
agent on
scan on
pair XX:XX:XX:XX:XX:XX   # 耳机 MAC
connect XX:XX:XX:XX:XX:XX
```

把蓝牙设为默认输出：

```bash
pactl list short sinks                                # 找到 bluez_output.XX_XX_XX_XX_XX_XX.1
pactl set-default-sink bluez_output.XX_XX_XX_XX_XX_XX.1
```

设成默认后，`audio.playback_device` 留空即可走蓝牙；要指定时，把 `pactl` 里看到的 sink 名填进去，或先 `python -c "import sounddevice as sd; print(sd.query_devices())"` 查 sounddevice 认到的名字/序号。
