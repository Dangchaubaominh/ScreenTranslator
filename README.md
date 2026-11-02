# ScreenTranslator

Translate on-screen Japanese, Chinese or Korean into English entirely on your own computer: nothing is sent online and no API key is needed. Built for visual novels, and for manga, manhua and manhwa read on the web.

> **Note:** the interface is in Vietnamese by default. To switch to English, open the `Cài đặt` (Settings) page, choose **English** under `Ngôn ngữ giao diện` (Interface language), then click `Bắt đầu` (Start) or `Lưu` (Save). The names below are the English ones.

## Features

- **Select region:** drag around a dialogue box and the translation appears right on top of it.
- **Live:** new lines in the region are translated automatically, with no key press.
- **Whole window:** translate menus, buttons or a full manga page. Each speech bubble gets its own box, including vertical text.
- **Three languages:** choose Japanese, Chinese or Korean on the Settings page. The app does not guess, because short text such as 設定 is written the same way in Japanese and Chinese.
- **Names:** list character names and terms so the model always translates them the same way.
- The model also sees the previous few lines of dialogue, so it can follow the conversation. Translated lines are cached and appear instantly next time.

## Requirements

| | |
|---|---|
| **Windows 11** | With a recent Snipping Tool, which provides the OCR engine |
| **[Ollama](https://ollama.com/download)** | Runs the translation model on your computer |
| **Translation model** | Japanese: [VNTL Gemma 2 2B](https://huggingface.co/lmg-anon/vntl-gemma2-2b-gguf), about 2.2 GB. Chinese and Korean: `qwen3.5:4b`, about 3.3 GB |
| **Graphics card** | Optional. The model also runs on the CPU, but more slowly |

## Installation

1. Download `ScreenTranslator.zip` from the [Releases](../../releases/latest) page and extract it to a permanent folder.
2. Install [Ollama](https://ollama.com/download).
3. Open a terminal and download the translation model for Japanese:

   ```bash
   ollama pull hf.co/lmg-anon/vntl-gemma2-2b-gguf:Q6_K
   ```

   For Chinese or Korean, download this one:

   ```bash
   ollama pull qwen3.5:4b
   ```

4. Open `ScreenTranslator.exe`. For Chinese or Korean, choose the language on the Settings page; the model changes with it.

The `.exe` is not code-signed, so Windows may show a SmartScreen warning. Click **More info**, then **Run anyway**. Some antivirus programs may also wrongly flag apps packaged with PyInstaller.

To open the app from the Start menu or the desktop, or start it with Windows, use the Settings page. If you move the app folder, create these shortcuts again: untick them, save, then tick them again.

## Hotkeys

You can change these on the Hotkeys page. Every action also has a button on the floating control panel.

| Key | Action |
|---|---|
| `Ctrl+Alt+T` | Select a new region and translate it |
| `Ctrl+Alt+F` | Translate the whole game window |
| `Ctrl+Alt+R` | Translate the previous region again |
| `Ctrl+Alt+L` | Live mode: translate new lines in the region automatically |
| `Ctrl+Alt+H` | Hide or show the translation |
| `Ctrl+Alt+E` | Edit the most recent OCR text |
| `Esc` | Clear the translation on screen, or turn off Live |

## Limitations

- It only translates into English. The models are small and sometimes get things wrong, especially names you have not listed.
- Chinese and Korean have had less testing than Japanese. Vertical Korean text is often misread, and closely stacked menu items may be read as one block.
- OneOCR is an undocumented internal Microsoft component. A future Snipping Tool update could change its files and stop OCR from working. If that happens, the app reports an error.
- Small text is enlarged and read a second time, which takes about twice as long.

## License

The source code is released under the [MIT License](LICENSE).

The packaged app includes PySide6 / Qt (LGPL-3.0) and other libraries; see [THIRD-PARTY-NOTICES.txt](packaging/THIRD-PARTY-NOTICES.txt). Neither this repository nor the packaged app contains the OneOCR files, Ollama or the translation model, which are covered by their owners' own terms.

This is a personal project and is not affiliated with Microsoft or Ollama.
