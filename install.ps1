py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Write-Host "Done. Activate next time with: .\.venv\Scripts\Activate.ps1"
