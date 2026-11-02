# ScreenTranslator

Translate on-screen Japanese into English entirely on your own computer: nothing is sent online and no API key is needed. Built for visual novels and manga read on the web.

> **Note:** the app's interface is in Vietnamese. Names from the interface appear below in Vietnamese, followed by their meaning.

## Features

- **Select a region** (`Chọn vùng`): drag around a dialogue box and the translation appears right on top of it.
- **Live:** new lines in the region are translated automatically, with no key press.
- **Whole window** (`Cả cửa sổ`): translate menus, buttons or a full manga page. Each speech bubble gets its own box, including vertical text.
- **Names and terms** (`Tên riêng`): list character names and terms so the model always translates them the same way.
- The model also sees the previous few lines of dialogue, so it can follow the conversation. Translated lines are cached and appear instantly next time.

## Requirements

| | |
|---|---|
| **Windows 11** | With a recent Snipping Tool, which provides the OCR engine |
| **[Ollama](https://ollama.com/download)** | Runs the translation model on your computer |
| **Translation model** | [VNTL Gemma 2 2B](https://huggingface.co/lmg-anon/vntl-gemma2-2b-gguf), about 2.2 GB |
| **Graphics card** | Optional. The model also runs on the CPU, but more slowly |

## Installation

1. Download `ScreenTranslator.zip` from the [Releases](../../releases/latest) page and extract it to a permanent folder.
2. Install [Ollama](https://ollama.com/download).
3. Open a terminal and download the translation model:

   ```bash
   ollama pull hf.co/lmg-anon/vntl-gemma2-2b-gguf:Q6_K
   ```

4. Open `ScreenTranslator.exe`.

The `.exe` is not code-signed, so Windows may show a SmartScreen warning. Click **More info**, then **Run anyway**. Some antivirus programs may also wrongly flag apps packaged with PyInstaller. If you would rather not run the packaged app, run it from source.

To open the app from the Start menu or the desktop, or start it with Windows, use the `Cài đặt` (Settings) page. If you move the app folder, create these shortcuts again: untick them, save, then tick them again.

## Hotkeys

You can change these on the `Phím tắt` (Hotkeys) page. Every action also has a button on the floating control panel.

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

- It only translates from Japanese to English. The model is small and sometimes gets things wrong, especially names you have not listed.
- OneOCR is an undocumented internal Microsoft component. A future Snipping Tool update could change its files and stop OCR from working. If that happens, the app reports an error.
- Small text is enlarged and read a second time, which takes about twice as long.

## Your data

- Settings, names and terms, the translation cache and the log are stored in `%APPDATA%\ScreenTranslator`.
- On first run, the app copies 3 OneOCR files (about 110 MB) from your own Snipping Tool to `%USERPROFILE%\.config\oneocr`.

To uninstall, delete the app folder, these two folders and any shortcuts you created.

## Running from source

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

```bash
uv run screen-translator
```

Run the tests:

```bash
uv run pytest
```

Build `dist/ScreenTranslator.zip`:

```bash
uv run --group build pyinstaller --noconfirm packaging/ScreenTranslator.spec
```

## License

The source code is released under the [MIT License](LICENSE).

The packaged app includes PySide6 / Qt (LGPL-3.0) and other libraries; see [THIRD-PARTY-NOTICES.txt](packaging/THIRD-PARTY-NOTICES.txt). Neither this repository nor the packaged app contains the OneOCR files, Ollama or the translation model, which are covered by their owners' own terms.

This is a personal project and is not affiliated with Microsoft or Ollama.
