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
