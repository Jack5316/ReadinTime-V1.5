"""
Runtime hook to locate bundled FFmpeg executables for audio processing.

This prefers real executables (ffmpeg.exe, ffprobe.exe) and adds their directory
to PATH. It also sets commonly used environment variables that downstream
libraries may check.
"""

import os
import sys
from pathlib import Path


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    # 1) PyInstaller onefile extraction dir
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS))  # type: ignore[attr-defined]
    # 2) Directory of the running executable
    try:
        candidates.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    # 2b) Original on-disk exe directory (argv[0]) for onefile
    try:
        launch_exe = Path(sys.argv[0]).resolve()
        if launch_exe.exists():
            candidates.append(launch_exe.parent)
            candidates.append(launch_exe.parent.parent)
            candidates.append(launch_exe.parent / "bin")
    except Exception:
        pass
    # 3) Electron win-unpacked layout: exe at win-unpacked/bin/*.exe, root has ffmpeg too
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([
            exe_dir,
            exe_dir.parent,                 # win-unpacked
            exe_dir.parent / "bin",        # win-unpacked/bin
            exe_dir.parent.parent,          # in case of nested
        ])
    except Exception:
        pass
    # 4) Custom override
    env_dir = os.environ.get("ARBOOKS_FFMPEG_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    return candidates


def _find_exe(names: list[str]) -> tuple[Path | None, Path | None]:
    for base in _candidate_dirs():
        for name in names:
            p = base / name
            if p.exists():
                return p, base
    # PATH lookup as a last resort
    for name in names:
        try:
            from shutil import which

            found = which(name)
            if found:
                p = Path(found)
                return p, p.parent
        except Exception:
            pass
    return None, None


def setup_ffmpeg_environment() -> bool:
    ffmpeg_path, ffmpeg_dir = _find_exe(["ffmpeg.exe", "ffmpeg"])
    ffprobe_path, ffprobe_dir = _find_exe(["ffprobe.exe", "ffprobe"])

    any_found = False
    target_dirs: list[str] = []

    if ffmpeg_path:
        print(f"[FFmpeg Runtime Hook] ffmpeg: {ffmpeg_path}")
        os.environ.setdefault("FFMPEG_BINARY", str(ffmpeg_path))
        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", str(ffmpeg_path))
        target_dirs.append(str(ffmpeg_path.parent))
        any_found = True
    if ffprobe_path:
        print(f"[FFmpeg Runtime Hook] ffprobe: {ffprobe_path}")
        os.environ.setdefault("FFPROBE_BINARY", str(ffprobe_path))
        target_dirs.append(str(ffprobe_path.parent))
        any_found = True

    # Prepend dirs to PATH for subprocess lookups
    if target_dirs:
        current_path = os.environ.get("PATH", "")
        for d in target_dirs:
            if d and d not in current_path:
                current_path = d + os.pathsep + current_path
        os.environ["PATH"] = current_path
        if target_dirs:
            os.environ.setdefault("FFMPEG_PATH", target_dirs[0])
        print(f"[FFmpeg Runtime Hook] PATH updated with: {target_dirs}")

    if not any_found:
        # Helpful diagnostics
        print("[FFmpeg Runtime Hook] Warning: Could not locate ffmpeg/ffprobe. Checked:")
        for c in _candidate_dirs():
            print(f"  - {c}")
    return any_found


# Execute on import by PyInstaller
setup_ffmpeg_environment()
