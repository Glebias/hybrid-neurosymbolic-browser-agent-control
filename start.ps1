$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:ANONYMIZED_TELEMETRY='false'
$env:PYTHONIOENCODING='utf-8'
& "$PSScriptRoot\.venv\Scripts\python.exe" -m uvicorn guard.app:app --host 127.0.0.1 --port 8765
