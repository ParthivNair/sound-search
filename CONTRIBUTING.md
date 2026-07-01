# Developing Forage (Windows + Anaconda)

> **Critical:** the machine's default `python` is **3.8.5 (EOL)** and there is a
> 32-bit 3.8 on the `py` launcher. `laion-clap`/`torch` require **Python ≥3.11**.
> Always work inside the dedicated `forage` conda env — never the system Python
> and never Anaconda `base` (CLAP's pins, e.g. `numpy<2`, can silently downgrade
> base packages you rely on).

## One-time environment setup (the canonical recipe)

`conda` is not on the Git Bash PATH here; it lives at
`C:\Users\Parthiv\anaconda3\Scripts\conda.exe`. From an **Anaconda Prompt**
(where `conda` is on PATH) the steps are:

```bat
conda create -n forage python=3.11 -y
conda install -n forage -c conda-forge ffmpeg -y

:: use the env's pip for everything else (keeps numpy management in pip only)
conda run -n forage python -m pip install --upgrade pip
conda run -n forage python -m pip install "numpy<2"
:: torchvision is an undeclared laion-clap import — install it from the same CPU index
conda run -n forage python -m pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu
conda run -n forage python -m pip install "laion-clap" "typer>=0.20" sqlite-vec requests soundfile librosa

:: install the forage package itself (editable)
conda run -n forage python -m pip install -e .
```

Why this order:
- **conda-forge ffmpeg** is a standalone binary (mp3/ogg decode fallback) and
  does not pull a conda `numpy`, so it can't fight the pip `numpy<2` pin.
- **`numpy<2` first**, then everything else, so a later wheel can't silently
  pull `numpy>=2` and break CLAP at import.
- **torch CPU-only** via the dedicated index URL — no multi-GB CUDA download
  (this machine has no GPU configured for v1).
- Audio is loaded/resampled with **`librosa`/`soundfile`**, never
  `torchaudio.resample` (fragile ffmpeg backend on Windows).

## Daily use

```bat
conda activate forage
forage config show
python scratch\clap_smoke.py
pytest
```

## Sanity check the install

```bat
conda run -n forage python -c "import numpy,torch,laion_clap,soundfile,librosa,typer,sqlite_vec,requests; print(numpy.__version__, torch.__version__)"
```

`numpy` must print a `1.x` version. If it prints `2.x`, run
`conda run -n forage python -m pip install "numpy<2"` again and re-check.

# Developing Forage (macOS, from source)

> **Critical:** use **Homebrew Python 3.12** — not the python.org installer and
> not Apple's system Python. Two reasons: `numpy<2` (a hard CLAP constraint) has
> no wheels past 3.12, so 3.13+ forces a source build; and the python.org macOS
> installers ship `sqlite3` **without loadable-extension support**
> (`Connection.enable_load_extension` missing), which crashes `sqlite-vec` at
> load time. Homebrew's Python has it enabled.

## One-time environment setup (the canonical recipe)

```zsh
brew install python@3.12 ffmpeg   # ffmpeg optional: mp3/ogg decode fallback (librosa/soundfile handle wav/flac/ogg natively)
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[gui,dev]"
```

Unlike the Windows recipe there is no CPU-index-URL dance — PyPI's default
torch wheels on Apple Silicon are already CPU-only arm64 (torch 2.12
verified). `numpy<2` resolves to 1.26.4 without any ordering tricks.

The ~1.9 GB CLAP checkpoint auto-downloads on first model use (first
`forage search`/`categorize`/`scratch/clap_smoke.py`) into the venv's
`site-packages/laion_clap/` — this is per-venv, so recreating the venv
re-downloads it.

PySide6 is uncapped on macOS (both 6.7.3 and 6.11.1 verified); the `<6.8` cap
in `pyproject.toml` is Windows-only.

## Daily use

```zsh
source .venv/bin/activate
forage config show
python scratch/clap_smoke.py
pytest
```

GUI tests run headless via `QT_QPA_PLATFORM=offscreen` automatically in the
suite.

## Sanity check the install

```zsh
python -c "import numpy,torch,laion_clap,soundfile,librosa,typer,sqlite_vec,requests; print(numpy.__version__, torch.__version__)"
python -c "import sqlite3; print(hasattr(sqlite3.connect(':memory:'), 'enable_load_extension'))"
```

`numpy` must print a `1.x` version. The second command must print `True` —
`False` means a wrong Python build (python.org or system Python); reinstall
via Homebrew.
