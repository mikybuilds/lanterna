# Builds dist\Lanterna\Lanterna.exe (folder build, fast start). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -m pip install --quiet ".[gui]" pyinstaller pillow
& $py packaging\make_icon.py
& $py -m PyInstaller --noconfirm --clean --windowed --name Lanterna `
    --icon packaging\lanterna.ico `
    --add-data "src\lanterna\ui;lanterna\ui" `
    --collect-submodules keyring `
    --collect-all webview `
    packaging\lanterna_gui.py
Write-Host "Built: dist\Lanterna\Lanterna.exe"

# Setup.exe when Inno Setup 6 is installed (the release workflow on GitHub always builds it)
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    $version = & $py -c "import lanterna; print(lanterna.__version__)"
    $homepage = & $py -c "import lanterna; print(lanterna.HOMEPAGE)"
    & $iscc "/DAppVersion=$version" "/DHomepage=$homepage" packaging\lanterna.iss
    Write-Host "Built: dist\Lanterna-Setup-$version.exe"
} else {
    Write-Host "Inno Setup 6 not found: skipped Setup.exe"
}
