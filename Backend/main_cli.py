"""Offline Chatterbox TTS CLI

This module provides a stable, offline-friendly CLI for generating speech from
text using the Chatterbox TTS model. It is designed to work consistently in
development, packaged Electron, and fully offline environments by:

- Resolving a shared Data directory for models and configs
- Merging configuration from Data/models.json over model-config.json
- Loading bundled models from Data/chatterbox_models when available
- Falling back to HuggingFace only when allowed (not forced offline)

OpenVINO support was removed to simplify deployment and reduce unused code
paths. The implementation relies on the PyTorch backend only.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _resolve_under(base: Path, val: str | None) -> str | None:
    """Resolve a potentially relative path under a base directory.

    - If ``val`` is absolute, it is returned as-is.
    - If ``val`` is relative, it is resolved under ``base``.
    - If ``val`` is falsy, returns None.
    """
    if not val:
        return None
    p = Path(val)
    return str(p if p.is_absolute() else (base / p))


def _find_data_dir() -> Path | None:
    """Locate the shared Data directory.

    Priority order:
    1) ARBOOKS_DATA_DIR env var (or ARBOOKS_DATA_PATH)
    2) Relative to executable (dist-cli/ -> backend-api/ -> repo root / Data)
    3) Relative to this file when running from source (repo root / Data)
    4) Current working directory / Data
    """
    env_dir = os.environ.get("ARBOOKS_DATA_DIR") or os.environ.get("ARBOOKS_DATA_PATH")
    if env_dir:
        p = Path(env_dir)
        if p.exists():
            return p
    # Executable location (Nuitka onefile places the exe in dist dir)
    try:
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidates = [
            exe_dir / "Data",                                # Data next to the .exe
            exe_dir.parent / "Data",                         # backend-api/Data when exe at backend-api/dist-cli/
            exe_dir.parent.parent / "Data",                   # arBooks/Data when exe at backend-api/dist-cli/
            exe_dir.parent / "resources" / "Data",          # Electron: bin/../resources/Data
            exe_dir.parent.parent / "resources" / "Data",   # Electron: bin/../../resources/Data
        ]
        for c in candidates:
            if c.exists():
                return c
    except Exception:
        pass
    # Source tree relative
    try:
        src_dir = Path(__file__).resolve().parent
        repo_data = src_dir.parent / "Data"
        if repo_data.exists():
            return repo_data
    except Exception:
        pass
    # CWD/Data
    cwd_data = Path.cwd() / "Data"
    if cwd_data.exists():
        return cwd_data
    return None


def _resolve_bundled_dir(bundled_dir_value: str | None, config_path: Path, data_dir: Path | None) -> Path:
    """Resolve the bundled models directory to an absolute path.

    Resolution order:
    1) If absolute path provided, return as-is
    2) ``Data/<bundled_dir>`` when Data dir is available and exists
    3) ``<config_dir>/<bundled_dir>`` when it exists next to config
    4) Fallback to ``Data/<bundled_dir>`` or ``<config_dir>/<bundled_dir>`` even if missing
    """
    candidate = bundled_dir_value or "chatterbox_models"
    cand_path = Path(candidate)
    
    # If it's an absolute path, return as-is
    if cand_path.is_absolute():
        return cand_path
    
    # Try to resolve relative to data_dir first (preferred)
    if data_dir is not None:
        resolved_path = (data_dir / cand_path).resolve()
        if resolved_path.exists():
            print(f"Found bundled models in: {resolved_path}")
            return resolved_path
    
    # Try relative to config file location
    if (config_path.parent / cand_path).exists():
        resolved_path = (config_path.parent / cand_path).resolve()
        print(f"Found bundled models in: {resolved_path}")
        return resolved_path
    
    # Fallback: return the expected path even if it doesn't exist yet
    if data_dir is not None:
        return (data_dir / cand_path).resolve()
    
    return (config_path.parent / cand_path).resolve()


def _load_effective_config(explicit_config_path: Path | None) -> tuple[dict, Path | None, Path | None]:
    """Load effective configuration for TTS models.

    Merges ``Data/models.json`` (section ``chatterbox``) over ``model-config.json``
    and normalizes any relative paths to the detected Data directory.

    Returns a tuple: ``(config_dict, resolved_config_path, data_dir)``.
    """
    data_dir = _find_data_dir()
    # Determine config path
    resolved_cfg: Path | None = None
    if explicit_config_path and explicit_config_path.exists():
        resolved_cfg = explicit_config_path
    else:
        # Prefer Data/model-config.json, then sibling model-config.json
        if data_dir and (data_dir / "model-config.json").exists():
            resolved_cfg = data_dir / "model-config.json"
        else:
            sibling = Path(__file__).with_name("model-config.json")
            if sibling.exists():
                resolved_cfg = sibling

    base_cfg: dict = {}
    if resolved_cfg and resolved_cfg.exists():
        with open(resolved_cfg, "r", encoding="utf-8") as f:
            try:
                base_cfg = json.load(f) or {}
            except Exception:
                base_cfg = {}

    # Optional overlay from Data/models.json -> section 'chatterbox'
    if data_dir and (data_dir / "models.json").exists():
        try:
            with open(data_dir / "models.json", "r", encoding="utf-8") as f:
                models_cfg = json.load(f) or {}
            ch_cfg = models_cfg.get("chatterbox") or {}
            # Only set keys not already present to respect explicit config
            for k in ("device", "source", "bundled_dir", "hf_repo", "target_sr"):
                if k not in base_cfg and k in ch_cfg:
                    base_cfg[k] = ch_cfg[k]
        except Exception:
            pass
    # Normalize any relative paths under Data/
    if data_dir:
        for key in ("bundled_dir", "models_dir"):
            if key in base_cfg and isinstance(base_cfg[key], str):
                base_cfg[key] = _resolve_under(data_dir, base_cfg[key])

    return base_cfg, resolved_cfg, data_dir

def load_tts_from_config(device: str, config_path: Path):
    """Construct and return a Chatterbox TTS model instance based on config.

    Behavior:
    - Adds Data/chatterbox/src to import path when available (prefers bundled src)
    - Merges config files and points HF caches to Data/chatterbox_models
    - Loads bundled models from Data when present; otherwise falls back to HF
    - Respects offline environment variables to avoid accidental downloads
    """
    # For compiled executable, try to find chatterbox in the same directory first
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_dir = Path(sys.executable).parent
        chatterbox_dir = exe_dir / "chatterbox"
        if chatterbox_dir.exists() and str(chatterbox_dir) not in sys.path:
            sys.path.insert(0, str(chatterbox_dir))
            print(f"Added chatterbox path for compiled executable: {chatterbox_dir}")
    
    # Prefer Data/chatterbox/src when present; when compiled, avoid repo chatterbox/src to ensure Data takes precedence
    try:
        data_dir_for_imports = _find_data_dir()
        if data_dir_for_imports is not None:
            data_ch_src = (data_dir_for_imports / "chatterbox" / "src").resolve()
            if data_ch_src.exists() and str(data_ch_src) not in sys.path:
                # Insert at front so Data version is preferred
                sys.path.insert(0, str(data_ch_src))
                print(f"Added Data chatterbox path: {data_ch_src}")
    except Exception:
        # Best-effort, non-fatal if Data is missing
        pass

    # Import from the canonical module path. Avoid fallback paths that confuse
    # static analysis tools like Nuitka during import following.
    try:
        from chatterbox.tts import ChatterboxTTS
    except ImportError as e:
        print(f"Failed to import ChatterboxTTS: {e}")
        print("Please ensure PyTorch and chatterbox dependencies are installed:")
        print("pip install torch torchaudio transformers safetensors")
        print("For compiled executable, ensure chatterbox/ folder is in the same directory as the .exe")
        raise SystemExit(1)

    # Merge Data/models.json over config, and resolve bundled_dir to Data when present
    cfg, resolved_cfg_path, data_dir = _load_effective_config(config_path)

    # Ensure HF caches are directed to Data/chatterbox_models when available
    try:
        if data_dir:
            bundled_dir = cfg.get("bundled_dir") or "chatterbox_models"
            models_dir = (data_dir / bundled_dir).resolve()
            models_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HOME", str(models_dir))
            os.environ.setdefault("TRANSFORMERS_CACHE", str(models_dir))
            os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(models_dir))
    except Exception:
        # Best-effort cache redirection
        pass

    # Final device selection (env/arg wins over file if provided)
    device = (device or cfg.get("device") or os.getenv("CHB_TTS_DEVICE") or "cpu").lower()
    source = (cfg.get("source") or "bundled").lower()

    if source == "bundled":
        bundled_dir_resolved = _resolve_bundled_dir(cfg.get("bundled_dir"), resolved_cfg_path or Path.cwd(), data_dir)
        print(f"Looking for bundled models in: {bundled_dir_resolved}")
        
        # Verify required files exist; if not, fall back to HF
        # Check for either t3_cfg.safetensors (new format) or conds.pt (legacy format)
        required_base = ["ve.safetensors", "s3gen.safetensors", "tokenizer.json"]
        t3_files = ["t3_cfg.safetensors", "conds.pt"]
        
        have_base = all((bundled_dir_resolved / f).exists() for f in required_base)
        have_t3 = any((bundled_dir_resolved / f).exists() for f in t3_files)
        have_all = have_base and have_t3
        
        if have_all:
            try:
                print(f"Loading bundled models from: {bundled_dir_resolved}")
                return ChatterboxTTS.from_local(str(bundled_dir_resolved), device)
            except Exception as e:
                print(f"Failed to load bundled models: {e}")
                # Check if we're in offline mode before attempting HuggingFace fallback
                if os.environ.get("CHB_FORCE_OFFLINE") == "1" or os.environ.get("HF_HUB_OFFLINE") == "1":
                    raise RuntimeError(f"Failed to load bundled models and offline mode is enabled. Cannot fallback to HuggingFace. Error: {e}")
                print("Falling back to HuggingFace repo...")
                return ChatterboxTTS.from_pretrained(device)
        
        print(f"Bundled models missing in {bundled_dir_resolved}; falling back to HuggingFace repo")
        # List what files are actually present for debugging
        if bundled_dir_resolved.exists():
            print(f"Files found in {bundled_dir_resolved}:")
            for f in bundled_dir_resolved.iterdir():
                print(f"  {f.name}")
        
        # Check if we're in offline mode before attempting HuggingFace download
        if os.environ.get("CHB_FORCE_OFFLINE") == "1" or os.environ.get("HF_HUB_OFFLINE") == "1":
            missing_files = []
            if not have_base:
                missing_files.extend([f for f in required_base if not (bundled_dir_resolved / f).exists()])
            if not have_t3:
                missing_files.append("t3_cfg.safetensors or conds.pt")
            raise RuntimeError(f"Bundled models missing files: {missing_files}. Offline mode is enabled, cannot download from HuggingFace.")
        
        return ChatterboxTTS.from_pretrained(device)

    return ChatterboxTTS.from_pretrained(device)


def main():
    """Entry point for the offline Chatterbox TTS CLI.

    Parses arguments, loads the TTS model according to config, generates speech,
    applies optional speed adjustment using librosa, and saves the output WAV.
    """
    parser = argparse.ArgumentParser(description="Offline Chatterbox TTS CLI")
    parser.add_argument("--text", required=False)
    parser.add_argument("--text-file", required=False, help="Path to a UTF-8 text file to read input from")
    parser.add_argument("--out", required=True)
    parser.add_argument("--prompt", required=False)
    parser.add_argument("--exaggeration", type=float, default=0.5)
    parser.add_argument("--cfg-weight", type=float, default=0.5)
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (0.5 = half speed, 1.0 = normal, 2.0 = double speed)")
    parser.add_argument(
        "--device", default=os.getenv("CHB_TTS_DEVICE", "cpu"), help="cpu|cuda|mps"
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("model-config.json")),
        help=(
            "Path to model-config.json. If omitted or missing, the CLI will look for Data/model-config.json "
            "or merge settings from Data/models.json (section 'chatterbox') when available."
        ),
    )
    args = parser.parse_args()

    # Lazy imports to speed startup a bit
    import torch
    HAS_TORCHAUDIO = True
    try:
        import torchaudio  # type: ignore
    except Exception:
        HAS_TORCHAUDIO = False

    model = load_tts_from_config(args.device, Path(args.config))

    # Load text from file if provided to avoid command-line length limits
    input_text = args.text
    if not input_text and args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            input_text = f.read()
    if not input_text:
        raise SystemExit("No input text provided. Use --text or --text-file.")

    wav = model.generate(
        input_text,
        audio_prompt_path=args.prompt,
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg_weight,
    )

    # Apply speed adjustment if not 1.0
    if args.speed != 1.0:
        try:
            import librosa
            wav_np = wav.squeeze(0).detach().cpu().numpy()
            # Use librosa to change speed while preserving pitch
            wav_speed_adjusted = librosa.effects.time_stretch(wav_np, rate=args.speed)
            wav = torch.from_numpy(wav_speed_adjusted).unsqueeze(0)
            print(f"Applied speed adjustment: {args.speed}x")
        except ImportError:
            print("Warning: librosa not available, speed adjustment skipped")
        except Exception as e:
            print(f"Warning: Speed adjustment failed: {e}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if HAS_TORCHAUDIO:
        # Save using torchaudio when available
        import torchaudio  # type: ignore
        torchaudio.save(str(out_path), wav, model.sr)
    else:
        # Fallback: save using wave + numpy (mono 16-bit)
        import numpy as np
        import wave
        wav_np = wav.squeeze(0).detach().cpu().numpy()
        wav_np = np.clip(wav_np, -1.0, 1.0)
        wav_int16 = (wav_np * 32767.0).astype(np.int16)
        with wave.open(str(out_path), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(int(model.sr))
            wf.writeframes(wav_int16.tobytes())
    # Print absolute path for callers
    print(str(out_path.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
