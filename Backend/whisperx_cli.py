import argparse
import json
import os
import sys
from pathlib import Path


def group_sentences(words, min_words: int = 8):
    segments = []
    current = []
    count = 0
    for w in words:
        txt = (w.get("text") or w.get("word") or "").strip()
        if not txt:
            continue
        start = float(w.get("start", 0))
        end = float(w.get("end", 0))
        current.append({"text": txt, "start": start, "end": end})
        count += 1
        if (txt.endswith(('.', '!', '?')) and count >= min_words) or count >= min_words * 2:
            seg_text = " ".join([c["text"] for c in current]).strip()
            segments.append({
                "text": seg_text,
                "start": current[0]["start"],
                "end": current[-1]["end"],
            })
            current = []
            count = 0
    if current:
        seg_text = " ".join([c["text"] for c in current]).strip()
        segments.append({
            "text": seg_text,
            "start": current[0]["start"],
            "end": current[-1]["end"],
        })
    return segments


def create_word_mappings(words):
    """Create word-wise mappings for real-time sync"""
    return [
        {
            "text": w.get("text", ""),
            "start": float(w.get("start", 0)),
            "end": float(w.get("end", 0)),
            "confidence": float(w.get("confidence", 0)),
        }
        for w in words
    ]


def _resolve_base_dir() -> Path:
    # Prefer the directory of this running module; for Nuitka onefile this is
    # the temporary extraction directory that also holds bundled data files.
    try:
        here = Path(__file__).resolve().parent
        if here.exists():
            return here
    except Exception:
        pass

    # Environment hints provided by onefile bootstrap
    temp_dir = os.environ.get("NUITKA_ONEFILE_TEMP_DIR")
    if temp_dir:
        p = Path(temp_dir)
        if p.exists():
            return p

    parent_dir = os.environ.get("NUITKA_ONEFILE_PARENT")
    if parent_dir:
        p = Path(parent_dir)
        if p.exists():
            return p

    # Frozen executable parent (standalone, non-onefile)
    if getattr(sys, "frozen", False):
        try:
            return Path(sys.argv[0]).resolve().parent
        except Exception:
            return Path(sys.argv[0]).parent

    # Fallback to source file directory
    return Path(__file__).parent


def _resolve_data_dir(base_dir: Path) -> Path:
    # Prefer explicit env vars
    for key in ("ARBOOKS_DATA_DIR", "ARBOOKS_DATA_PATH", "DATA_DIR"):
        val = os.environ.get(key)
        if val:
            p = Path(val)
            if p.exists():
                return p
    # Try common locations relative to executable
    try:
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidates = [
            exe_dir.parent.parent / "Data",                 # arBooks/Data when exe at backend-api/dist-cli/
            exe_dir.parent / "Data",                        # fallback: backend-api/Data
            base_dir / "Data",
            exe_dir.parent / "resources" / "Data",        # Electron: bin/../resources/Data
            exe_dir.parent.parent / "resources" / "Data", # Electron: bin/../../resources/Data
        ]
        for c in candidates:
            if c.exists():
                return c
    except Exception:
        pass
    # Try source tree and cwd
    try:
        src_dir = Path(__file__).resolve().parent
        repo_data = src_dir.parent.parent / "Data"
        if repo_data.exists():
            return repo_data
    except Exception:
        pass
    cwd_data = Path.cwd() / "Data"
    if cwd_data.exists():
        return cwd_data
    # Fallback next to base_dir
    return base_dir / "Data"


def _load_models_config(data_dir: Path) -> dict:
    cfg_path = data_dir / "models.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    # defaults
    return {
        "whisperx": {
            "device": "cpu",
            "models_dir": str(data_dir / "whisperx_models"),
            "asr_model": "small",
            "compute_type": "int8",
            "batch_size": 4
        }
    }


def _maybe_add_local_whisperx(base_dir: Path) -> None:
    # If bundled source exists, add its PARENT directory to sys.path so that
    # `import whisperx` resolves package modules like `whisperx.audio`.
    try:
        # Case 1: Onefile build with data dir mapped as base_dir/whisperx
        pkg_dir = base_dir / "whisperx"
        if (pkg_dir / "__init__.py").exists():
            parent = base_dir
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return

        # Case 2: Bundled source under base_dir/whisperX-3.4.2/whisperx
        src_parent = base_dir / "whisperX-3.4.2"
        if (src_parent / "whisperx" / "__init__.py").exists():
            if str(src_parent) not in sys.path:
                sys.path.insert(0, str(src_parent))
            return

        # Fallback: if directories exist, still add reasonable parents
        for candidate in [src_parent, pkg_dir]:
            if candidate.exists():
                parent = candidate if candidate.name != "whisperx" else candidate.parent
                if str(parent) not in sys.path:
                    sys.path.insert(0, str(parent))
                return
    except Exception:
        # Non-fatal; import failure will be handled by caller
        pass


def main():
    parser = argparse.ArgumentParser(description="Offline WhisperX transcription CLI")
    parser.add_argument("--audio", required=False, help="Path to input audio file (wav)")
    parser.add_argument("--outdir", required=False, help="Output directory")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--print-config", action="store_true", help="Print resolved config and exit")
    parser.add_argument("--output-format", choices=["words", "sentences", "both"], default="both", 
                       help="Output format: words (for real-time sync), sentences (for reading), or both")
    args = parser.parse_args()

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    base_dir = _resolve_base_dir()
    data_dir = _resolve_data_dir(base_dir)
    cfg = _load_models_config(data_dir)
    wx_cfg = cfg.get("whisperx", {})

    # Prefer models directory from config, else Data/whisperx_models
    raw_models_dir = wx_cfg.get("models_dir", "whisperx_models")
    models_path = Path(raw_models_dir)
    models_dir = models_path if models_path.is_absolute() else (data_dir / models_path)
    if models_dir.exists():
        os.environ.setdefault("HF_HOME", str(models_dir))
        os.environ.setdefault("TRANSFORMERS_CACHE", str(models_dir))
        os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(models_dir))
        os.environ.setdefault("CT2_CACHES_DIR", str(models_dir))
        download_root = str(models_dir)
    else:
        download_root = None

    # Try to resolve a local snapshot directory for the ASR model to avoid network access
    local_model_dir = None
    try:
        asr_model_name_for_local = wx_cfg.get("asr_model", "small")
        preferred_snapshots_root = models_dir / f"models--Systran--faster-whisper-{asr_model_name_for_local}" / "snapshots"
        candidates = []
        if preferred_snapshots_root.exists():
            candidates = [p for p in preferred_snapshots_root.iterdir() if p.is_dir()]
        if not candidates:
            # Fallback: any faster-whisper snapshot present
            candidates = [p for p in models_dir.glob("models--Systran--faster-whisper*/snapshots/*") if p.is_dir()]
        for c in candidates:
            if (c / "model.bin").exists():
                local_model_dir = c
                break
    except Exception:
        # Best-effort; fall back to standard loading if detection fails
        pass

    # Dev utility: print resolved config without importing whisperx or requiring audio
    if args.print_config:
        summary = {
            "base_dir": str(base_dir),
            "data_dir": str(data_dir),
            "whisperx_config": wx_cfg,
            "models_dir": str(models_dir),
            "download_root": download_root,
            "local_snapshot_dir": (str(local_model_dir) if local_model_dir else None),
        }
        print(json.dumps(summary, indent=2))
        return 0

    if not args.audio or not args.outdir:
        print("--audio and --outdir are required unless --print-config is used", file=sys.stderr)
        return 2

    # Check if audio file exists
    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"ERROR: Audio file not found: {audio_path}", file=sys.stderr)
        print(f"Current working directory: {Path.cwd()}", file=sys.stderr)
        print(f"Absolute path: {audio_path.resolve()}", file=sys.stderr)
        return 1
    
    if not audio_path.is_file():
        print(f"ERROR: Audio path is not a file: {audio_path}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Allow importing bundled whisperx source if provided
    _maybe_add_local_whisperx(base_dir)

    try:
        import whisperx  # type: ignore
    except Exception as e:
        print(f"ERROR: whisperx not available: {e}")
        return 1

    # Load and transcribe
    try:
        # Check if we have FFmpeg available via environment variables set by runtime hook
        ffmpeg_binary = os.environ.get('FFMPEG_BINARY')
        ffmpeg_path = os.environ.get('FFMPEG_PATH')
        
        if ffmpeg_binary and ffmpeg_path:
            print(f"Using FFmpeg from runtime hook: {ffmpeg_binary}")
            # Ensure the directory is in PATH for subprocess calls
            current_path = os.environ.get('PATH', '')
            if ffmpeg_path not in current_path:
                os.environ['PATH'] = ffmpeg_path + os.pathsep + current_path
                print(f"Added FFmpeg path to environment: {ffmpeg_path}")
        
        audio = whisperx.load_audio(args.audio)
    except Exception as e:
        print(f"WARNING: whisperx.load_audio failed: {e}")
        print("Attempting fallback audio loading methods...")
        
        # Fallback 1: Try using librosa directly
        try:
            import librosa
            print("Using librosa fallback for audio loading...")
            audio, sr = librosa.load(args.audio, sr=16000)  # WhisperX expects 16kHz
            print(f"Successfully loaded audio with librosa: {len(audio)} samples at {sr}Hz")
        except Exception as librosa_error:
            print(f"librosa fallback failed: {librosa_error}")
            
            # Fallback 2: Try using soundfile directly
            try:
                import soundfile as sf
                print("Using soundfile fallback for audio loading...")
                audio, sr = sf.read(args.audio)
                if len(audio.shape) > 1:  # Convert stereo to mono
                    audio = audio.mean(axis=1)
                if sr != 16000:  # Resample if needed
                    import librosa
                    audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
                print(f"Successfully loaded audio with soundfile: {len(audio)} samples at 16kHz")
            except Exception as sf_error:
                print(f"soundfile fallback failed: {sf_error}")
                
                # Fallback 3: Try using torchaudio
                try:
                    import torch  # ensure torch is present before torchaudio ops
                    import torchaudio
                    print("Using torchaudio fallback for audio loading...")
                    audio, sr = torchaudio.load(args.audio)
                    audio = audio.numpy().flatten()  # Convert to numpy array
                    if len(audio.shape) > 1:  # Convert stereo to mono
                        audio = audio.mean(axis=0)
                    if sr != 16000:  # Resample if needed
                        resampler = torchaudio.transforms.Resample(sr, 16000)
                        audio = resampler(torch.tensor(audio)).numpy()
                    print(f"Successfully loaded audio with torchaudio: {len(audio)} samples at 16kHz")
                except Exception as ta_error:
                    print(f"torchaudio fallback failed: {ta_error}")
                    print("ERROR: All audio loading methods failed. Cannot proceed with transcription.")
                    print("Please ensure the audio file is valid and one of these audio libraries is available:")
                    print("  - FFmpeg (for whisperx.load_audio)")
                    print("  - librosa")
                    print("  - soundfile")
                    print("  - torchaudio")
                    return 1

    asr_model = wx_cfg.get("asr_model", "small")
    device = wx_cfg.get("device", "cpu")
    compute_type = wx_cfg.get("compute_type", "int8")
    batch_size = int(wx_cfg.get("batch_size", 4))

    if local_model_dir:
        # Load directly from local snapshot directory (fully offline)
        model = whisperx.load_model(str(local_model_dir), device=device, compute_type=compute_type)
    elif download_root:
        model = whisperx.load_model(asr_model, device=device, compute_type=compute_type, download_root=download_root)
    else:
        model = whisperx.load_model(asr_model, device=device, compute_type=compute_type)

    transcribe_language = None if args.language == "auto" else args.language
    if transcribe_language:
        result = model.transcribe(audio, batch_size=batch_size, language=transcribe_language)  # type: ignore
    else:
        result = model.transcribe(audio, batch_size=batch_size)  # type: ignore

    # Optional alignment
    language = result.get("language")
    segments_for_align = result.get("segments") or []
    if (
        bool(wx_cfg.get("align", True))
        and segments_for_align
        and language in ["en", "fr", "de", "es", "it", "ja", "zh", "nl", "uk", "pt"]
    ):
        # Alignment API expects model_dir, not download_root
        model_dir_arg = {"model_dir": str(models_dir)} if models_dir.exists() else {}
        model_a, metadata = whisperx.load_align_model(language_code=language, device=device, **model_dir_arg)
        result = whisperx.align(segments_for_align, model_a, metadata, audio, device=device, return_char_alignments=False)

    segments = result.get("segments", [])
    words = []
    for seg in segments:
        for w in seg.get("words", []):
            words.append({
                "text": w.get("word", ""),
                "start": float(w.get("start", 0)),
                "end": float(w.get("end", 0)),
                "confidence": float(w.get("score", 0)),
            })

    # Generate output based on requested format
    if args.output_format == "words":
        mappings = create_word_mappings(words)
        with open(outdir / "text_mappings.json", "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
    elif args.output_format == "sentences":
        mappings = group_sentences(words)
        with open(outdir / "text_mappings.json", "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2)
    else:  # both
        word_mappings = create_word_mappings(words)
        sentence_mappings = group_sentences(words)
        
        with open(outdir / "text_mappings_words.json", "w", encoding="utf-8") as f:
            json.dump(word_mappings, f, indent=2)
        
        with open(outdir / "text_mappings_sentences.json", "w", encoding="utf-8") as f:
            json.dump(sentence_mappings, f, indent=2)
        
        # For backward compatibility, also create text_mappings.json with word mappings
        with open(outdir / "text_mappings.json", "w", encoding="utf-8") as f:
            json.dump(word_mappings, f, indent=2)

    with open(outdir / "transcription.json", "w", encoding="utf-8") as f:
        json.dump({"language": language, "segments": segments, "words": words}, f, indent=2)

    if args.output_format == "both":
        print(f"Generated both formats:")
        print(f"  Word-wise: {str((outdir / 'text_mappings_words.json').resolve())}")
        print(f"  Sentence-wise: {str((outdir / 'text_mappings_sentences.json').resolve())}")
        print(f"  Default (word-wise): {str((outdir / 'text_mappings.json').resolve())}")
    else:
        print(str((outdir / "text_mappings.json").resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())


