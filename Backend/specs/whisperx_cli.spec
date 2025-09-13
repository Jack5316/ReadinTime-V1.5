# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

SPEC_DIR = Path.cwd()   # you're invoking PyInstaller in the 'specs' folder
BASE_DIR = SPEC_DIR.parent
SCRIPT = BASE_DIR / "whisperx_cli.py"  # Define the script path

# ---- 1) Collect everything for packages that use dynamic imports or ship data ----
PKGS_COLLECT_ALL = [
    "whisperx",
    "faster_whisper",
    "ctranslate2",
    "torch",
    "pyannote",            # meta namespace
    "pyannote.audio",
    "pyannote.core",
    "speechbrain",
    "lightning_fabric",
    "pytorch_lightning",
    "asteroid_filterbanks",
    "torchaudio",
    "transformers",
    "librosa",
    "soundfile",
    "tokenizers",
    "sentencepiece",       # optional; include if installed/used
    "matplotlib",
    "numpy",
]

datas, binaries, hiddenimports = [], [], []

for pkg in PKGS_COLLECT_ALL:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        # some packages may not be installed; skip silently
        pass

# ---- 2) Force-include dynamic submodules that collect_all can miss ----
hiddenimports += collect_submodules("whisperx.vads")
hiddenimports += collect_submodules("pyannote.audio.pipelines")
hiddenimports += collect_submodules("pyannote.audio.models")
hiddenimports += collect_submodules("pyannote.audio.core")
hiddenimports += collect_submodules("speechbrain")
hiddenimports += collect_submodules("torch")

# Deduplicate
hiddenimports = sorted(set(hiddenimports))

# ---- 3) Bundle FFmpeg to fix audio loading issues ----
# FFmpeg is required by whisperx.load_audio() for audio processing
# We'll try to find FFmpeg in common locations and bundle it
import os
import shutil
import subprocess

def find_ffmpeg():
    """Find FFmpeg executable in common locations"""
    ffmpeg_names = ['ffmpeg.exe', 'ffmpeg']
    search_paths = []

    # Check if ffmpeg is in PATH
    for name in ffmpeg_names:
        try:
            result = subprocess.run([name, '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                which_path = shutil.which(name)
                if which_path:
                    return which_path
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            continue

    # Check common installation directories and repo-local bins
    if os.name == 'nt':  # Windows
        search_paths.extend([
            str((BASE_DIR.parent / 'arbooks-desktop' / 'bin').resolve()),
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files (x86)\ffmpeg\bin",
            os.path.expanduser(r"~\ffmpeg\bin"),
            os.path.expanduser(r"~\AppData\Local\ffmpeg\bin"),
        ])
    else:  # Unix-like
        search_paths.extend([
            "/usr/bin",
            "/usr/local/bin",
            "/opt/ffmpeg/bin",
            os.path.expanduser("~/ffmpeg/bin"),
        ])

    for path in search_paths:
        if os.path.exists(path):
            for name in ffmpeg_names:
                ffmpeg_path = os.path.join(path, name)
                if os.path.isfile(ffmpeg_path) and os.access(ffmpeg_path, os.X_OK):
                    return ffmpeg_path

    return None

def find_ffprobe():
    """Find FFprobe executable in common locations"""
    probe_names = ['ffprobe.exe', 'ffprobe']
    search_paths = []

    # Check PATH first
    for name in probe_names:
        try:
            result = subprocess.run([name, '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                which_path = shutil.which(name)
                if which_path:
                    return which_path
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            continue

    # Known locations
    if os.name == 'nt':
        search_paths.extend([
            str((BASE_DIR.parent / 'arbooks-desktop' / 'bin').resolve()),
            r"C:\ffmpeg\bin",
            r"C:\Program Files\ffmpeg\bin",
            r"C:\Program Files (x86)\ffmpeg\bin",
            os.path.expanduser(r"~\ffmpeg\bin"),
            os.path.expanduser(r"~\AppData\Local\ffmpeg\bin"),
        ])
    else:
        search_paths.extend([
            "/usr/bin",
            "/usr/local/bin",
            "/opt/ffmpeg/bin",
            os.path.expanduser("~/ffmpeg/bin"),
        ])

    for path in search_paths:
        if os.path.exists(path):
            for name in probe_names:
                probe_path = os.path.join(path, name)
                if os.path.isfile(probe_path) and os.access(probe_path, os.X_OK):
                    return probe_path
    return None

def find_ffmpeg_dll():
    """Find FFmpeg DLL in the distribution or common locations"""
    # Check if we're in a distribution context
    if os.path.exists("ffmpeg.dll"):
        return "ffmpeg.dll"
    
    # Check parent directories for win-unpacked structure
    current_dir = Path.cwd()
    for parent in [current_dir.parent, current_dir.parent.parent, current_dir.parent.parent.parent]:
        ffmpeg_dll = parent / "ffmpeg.dll"
        if ffmpeg_dll.exists():
            return str(ffmpeg_dll)
    
    # Check common Windows system directories
    system32 = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32')
    if os.path.exists(os.path.join(system32, 'ffmpeg.dll')):
        return os.path.join(system32, 'ffmpeg.dll')
    
    return None

# Try to find and bundle FFmpeg + FFprobe
ffmpeg_path = find_ffmpeg()
ffprobe_path = find_ffprobe()
ffmpeg_dll = find_ffmpeg_dll()

if ffmpeg_path:
    print(f"Found FFmpeg executable at: {ffmpeg_path}")
    binaries.append((ffmpeg_path, '.'))
    if ffprobe_path:
        print(f"Found FFprobe executable at: {ffprobe_path}")
        binaries.append((ffprobe_path, '.'))
elif ffmpeg_dll:
    print(f"Found FFmpeg DLL at: {ffmpeg_dll}")
    datas.append((ffmpeg_dll, '.'))
    print("Note: FFmpeg DLL found. The executable will need to be configured to use it.")
    if ffprobe_path:
        print(f"Found FFprobe executable at: {ffprobe_path}")
        binaries.append((ffprobe_path, '.'))
else:
    print("WARNING: FFmpeg not found. Audio processing may fail on target machines.")
    print("Consider installing FFmpeg or ensuring it's in PATH.")

# ---- 4) Optional runtime hook to give pyannote a writable cache (Onefile unpack dir is read-only) ----
# Create a file at BASE_DIR/hooks/rt_pyannote_cache.py with:
#   import os, tempfile
#   os.environ.setdefault("PYANNOTE_CACHE", os.path.join(tempfile.gettempdir(), "pyannote"))
runtime_hooks = [
    str(BASE_DIR / "hooks" / "rt_pyannote_cache.py"),
    str(BASE_DIR / "hooks" / "rt_ffmpeg_dll.py")  # FFmpeg DLL runtime hook
]

block_cipher = None

a = Analysis(
    [str(SCRIPT)],
    pathex=[str(BASE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(BASE_DIR / "hooks")],   # where your runtime hook lives
    runtime_hooks=runtime_hooks,
    excludes=[
        # trim fat you don't use
        "tensorflow", "jax", "onnxruntime-gpu", "torchvision",  # drop if you actually need them
        "pyannote.database",  # often unused; remove if you rely on it
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="whisperx_cli",
    console=True,
    debug=False,
    upx=True,
    upx_exclude=[],
    strip=False,
    bootloader_ignore_signals=False,
    onefile=True,  # build ONEFOLDER first to debug; switch to True after it's stable
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="whisperx_cli",
)
