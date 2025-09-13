import os, tempfile
os.environ.setdefault("PYANNOTE_CACHE", os.path.join(tempfile.gettempdir(), "pyannote"))