# No parameters needed - just copies existing executables and Data folder

# Resolve important directories robustly
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path (Resolve-Path $ScriptDir) '..\..')).Path
$BackendDir = (Resolve-Path (Join-Path (Resolve-Path $ScriptDir) '..')).Path
$SpecsDir = Join-Path $BackendDir 'specs'
$DesktopDir = Join-Path $RepoRoot 'ReadinTime_Voice_Desktop'
$BinDir = Join-Path $DesktopDir 'bin'
$ResourcesDir = Join-Path $DesktopDir 'resources'
$ResourcesDataDir = Join-Path $ResourcesDir 'Data'

# Try to find local ffmpeg binaries (windows)
$RepoFfmpegDirCandidates = @(
    (Join-Path $RepoRoot 'ffmpeg'),
    (Join-Path $RepoRoot 'ffmpeg\bin'),
    'C:\\ffmpeg\\bin',
    'C:\\Program Files\\ffmpeg\\bin',
    'C:\\Program Files (x86)\\ffmpeg\\bin'
)

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
New-Item -ItemType Directory -Force -Path $ResourcesDataDir | Out-Null

Write-Host "Copying existing executables from backend-api/specs/dist/" -ForegroundColor Cyan

# Copy existing executables from backend-api/specs/dist/
$BackendDistDir = Join-Path $BackendDir 'specs\dist'
$MainExe = Get-ChildItem -Path $BackendDistDir -Filter 'main_cli.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
$WxExe = Get-ChildItem -Path $BackendDistDir -Filter 'whisperx_cli.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
$PdfExe = Get-ChildItem -Path $BackendDistDir -Filter 'pdf_cli.exe' -ErrorAction SilentlyContinue | Select-Object -First 1

if ($MainExe) {
    Copy-Item -Force $MainExe.FullName (Join-Path $BinDir 'main_cli.exe')
    Write-Host "Staged main_cli.exe -> $BinDir" -ForegroundColor Green
} else {
    Write-Warning "main_cli.exe not found under $BackendDistDir"
}

if ($WxExe) {
    Copy-Item -Force $WxExe.FullName (Join-Path $BinDir 'whisperx_cli.exe')
    Write-Host "Staged whisperx_cli.exe -> $BinDir" -ForegroundColor Green
} else {
    Write-Warning "whisperx_cli.exe not found under $BackendDistDir"
}

if ($PdfExe) {
    Copy-Item -Force $PdfExe.FullName (Join-Path $BinDir 'pdf_cli.exe')
    Write-Host "Staged pdf_cli.exe -> $BinDir" -ForegroundColor Green
} else {
    Write-Warning "pdf_cli.exe not found under $BackendDistDir"
}

# Stage ffmpeg and ffprobe if available
foreach ($cand in $RepoFfmpegDirCandidates) {
    if (Test-Path $cand) {
        $ffmpeg = Join-Path $cand 'ffmpeg.exe'
        $ffprobe = Join-Path $cand 'ffprobe.exe'
        if (Test-Path $ffmpeg) {
            Copy-Item -Force $ffmpeg (Join-Path $BinDir 'ffmpeg.exe')
            Write-Host "Staged ffmpeg.exe -> $BinDir" -ForegroundColor Green
        }
        if (Test-Path $ffprobe) {
            Copy-Item -Force $ffprobe (Join-Path $BinDir 'ffprobe.exe')
            Write-Host "Staged ffprobe.exe -> $BinDir" -ForegroundColor Green
        }
        break
    }
}

# Fallback: discover ffmpeg/ffprobe from PATH if not already staged
if (-not (Test-Path (Join-Path $BinDir 'ffmpeg.exe')) -or -not (Test-Path (Join-Path $BinDir 'ffprobe.exe'))) {
    $ffmpegCmd = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)
    $ffprobeCmd = (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)
    if ($ffmpegCmd -and -not (Test-Path (Join-Path $BinDir 'ffmpeg.exe'))) {
        try {
            Copy-Item -Force $ffmpegCmd.Source (Join-Path $BinDir 'ffmpeg.exe')
            Write-Host "Staged ffmpeg.exe from PATH -> $BinDir" -ForegroundColor Green
        } catch { Write-Warning "Failed to copy ffmpeg.exe from PATH: $($_.Exception.Message)" }
    }
    if ($ffprobeCmd -and -not (Test-Path (Join-Path $BinDir 'ffprobe.exe'))) {
        try {
            Copy-Item -Force $ffprobeCmd.Source (Join-Path $BinDir 'ffprobe.exe')
            Write-Host "Staged ffprobe.exe from PATH -> $BinDir" -ForegroundColor Green
        } catch { Write-Warning "Failed to copy ffprobe.exe from PATH: $($_.Exception.Message)" }
    }
}

# Copy ONLY required Data assets to resources/Data for packaging
$RepoData = Join-Path $RepoRoot 'Data'
if (Test-Path $RepoData) {
    Write-Host "Staging minimal Data -> $ResourcesDataDir" -ForegroundColor Cyan

    # Ensure target exists
    New-Item -ItemType Directory -Force -Path $ResourcesDataDir | Out-Null

    # 1) models.json (top-level)
    $ModelsJson = Join-Path $RepoData 'models.json'
    if (Test-Path $ModelsJson) {
        Copy-Item -Force $ModelsJson (Join-Path $ResourcesDataDir 'models.json')
        Write-Host "Copied models.json" -ForegroundColor Green
    } else {
        Write-Warning "models.json not found at $ModelsJson"
    }

    # 2) chatterbox_models (weights only: exclude cache dirs like blobs/refs)
    $ChatterboxSrc = Join-Path $RepoData 'chatterbox_models'
    if (Test-Path $ChatterboxSrc) {
        $ChatterboxDst = Join-Path $ResourcesDataDir 'chatterbox_models'
        New-Item -ItemType Directory -Force -Path $ChatterboxDst | Out-Null
        robocopy $ChatterboxSrc $ChatterboxDst /E /XD blobs refs /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -le 3) {
            Write-Host "Copied chatterbox_models (excluding blobs/refs)" -ForegroundColor Green
        } else {
            Write-Warning "robocopy reported issues copying chatterbox_models (code $LASTEXITCODE)"
        }
    } else {
        Write-Warning "chatterbox_models not found at $ChatterboxSrc"
    }

    # 3) whisperx_models (weights only: exclude blobs/refs and giant wav2vec2 .pth)
    $WxSrc = Join-Path $RepoData 'whisperx_models'
    if (Test-Path $WxSrc) {
        $WxDst = Join-Path $ResourcesDataDir 'whisperx_models'
        New-Item -ItemType Directory -Force -Path $WxDst | Out-Null
        # First copy structure excluding cache dirs
        robocopy $WxSrc $WxDst /E /XD blobs refs /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -le 3) {
            Write-Host "Copied whisperx_models (excluding blobs/refs)" -ForegroundColor Green
        } else {
            Write-Warning "robocopy reported issues copying whisperx_models (code $LASTEXITCODE)"
        }
        # Keep the wav2vec2 alignment model - it's essential for word-level alignment
        # The file is already copied by robocopy above
    } else {
        Write-Warning "whisperx_models not found at $WxSrc"
    }

    Write-Host "Minimal Data staging complete." -ForegroundColor Green
} else {
    Write-Warning "Data folder not found at $RepoData"
}

exit 0


