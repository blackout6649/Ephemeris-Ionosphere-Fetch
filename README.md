# NASA CDDIS GNSS Ephemeris Downloader

A Python script to download NASA CDDIS GNSS broadcast ephemeris files reliably on Windows corporate environments.

## Supported File Types

- **GPS RINEX V2 BRDC**: `brdcDDD0.YYn.gz` from `https://cddis.nasa.gov/archive/gnss/data/daily/YYYY/DDD/YYn/`
- **RINEX V3 Multi-GNSS BRDM**: `BRDM00DLR_S_YYYYDDD0000_01D_MN.rnx.gz` from `https://cddis.nasa.gov/archive/gnss/data/daily/YYYY/brdc/`

Where `YYYY` = 4-digit year, `DDD` = day-of-year (001-366), `YY` = 2-digit year.

## Setup (No PowerShell Scripts Required)

### 1. Create Virtual Environment

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt
```

### 2. Create NASA Earthdata Credentials

You need a free NASA Earthdata account. Sign up at https://urs.earthdata.nasa.gov/

**Option A: Netrc File (Recommended)**

Create file: `C:\Users\<YourUsername>\_netrc` (no file extension)

Contents:
```
machine urs.earthdata.nasa.gov
    login YOUR_USERNAME
    password YOUR_PASSWORD
```

**Option B: Environment Variables**

```powershell
$env:EARTHDATA_USERNAME="your_username"
$env:EARTHDATA_PASSWORD="your_password"
```

**Option C: Custom Netrc Location**

```powershell
$env:NETRC="$env:USERPROFILE\_netrc"
```

### 3. First-Time CDDIS Authorization

Visit https://cddis.nasa.gov in a web browser and sign in once with your NASA Earthdata account to authorize CDDIS access.

## Usage Examples

### Single Day Download

```powershell
# GPS RINEX V2 with decompression
.\.venv\Scripts\python.exe download_cddis_ephemeris.py --date 2025-09-18 --type gps-v2 --out .\data --decompress

# RINEX V3 Multi-GNSS
.\.venv\Scripts\python.exe download_cddis_ephemeris.py --date 2025-09-18 --type brdm-v3 --out .\data
```

### Date Range Download

```powershell
# Download week of data, skip existing files, verbose output
.\.venv\Scripts\python.exe download_cddis_ephemeris.py --start 2025-09-15 --end 2025-09-21 --type gps-v2 --out .\data --skip-existing --verbose
```

### Command Line Options

- `--date YYYY-MM-DD`: Download single date
- `--start YYYY-MM-DD --end YYYY-MM-DD`: Download date range
- `--type {gps-v2, brdm-v3}`: File type to download
- `--out PATH`: Output directory (default: current directory)
- `--decompress`: Decompress .gz files after download
- `--skip-existing`: Skip files that already exist
- `--retries N`: Number of retry attempts (default: 3)
- `--timeout SECONDS`: Request timeout (default: 60)
- `--proxy URL`: Proxy server URL
- `--verbose`: Enable verbose logging
- `--diagnose`: Print environment diagnostics

## File Organization

Downloaded files are organized as:
```
output_dir/
  2025/
    brdc262.25n.gz          # GPS RINEX V2
    BRDM00DLR_S_20252620000_01D_MN.rnx.gz  # RINEX V3
  logs/
    ephemeris_downloader.log
```

## Corporate Environment Support

### Proxy Configuration

```powershell
# Set proxy environment variables
$env:HTTPS_PROXY="https://user:pass@proxy.company.com:443"
$env:HTTP_PROXY="http://proxy.company.com:8080"

# Or use --proxy flag
.\.venv\Scripts\python.exe download_cddis_ephemeris.py --proxy https://proxy.company.com:443 --date 2025-09-18
```

### TLS/SSL Issues

```powershell
# Point to corporate CA bundle
$env:REQUESTS_CA_BUNDLE="C:\path\to\corporate-ca.pem"
```

### PowerShell Execution Policy

If you need to run PowerShell scripts but are blocked by policy:

```powershell
# Temporarily bypass for current session
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Remove Mark-of-the-Web from downloaded files
Unblock-File .\downloaded_script.ps1
```

## Troubleshooting

### Run Diagnostics

```powershell
.\.venv\Scripts\python.exe download_cddis_ephemeris.py --diagnose
```

This shows:
- Python executable location
- Home directory resolution
- Netrc file locations and status
- Environment variables
- Credential discovery results (no passwords shown)

### Common Issues

**Authentication Errors (401/403)**
- Verify NASA Earthdata credentials
- Visit https://cddis.nasa.gov and sign in once
- Check netrc file format (no file extension on Windows)

**File Not Found (404)**
- Normal for recent dates - files may not be available yet
- CDDIS typically has 1-3 day delay for recent data

**SSL/Network Errors**
- Set `REQUESTS_CA_BUNDLE` for corporate CA certificates
- Configure proxy settings via environment variables or `--proxy`

**Credential Discovery Issues**
- Use `--diagnose` to see which paths are checked
- Ensure `_netrc` file is in the correct location
- Try environment variables as fallback

### Return Codes

- `0`: Success (including 404-skipped files)
- `1`: Authentication, network, or configuration errors

## Requirements

- Python 3.9+
- Windows (with limited PowerShell if needed) or POSIX systems
- NASA Earthdata account with CDDIS access

## Security Notes

- Passwords are never logged or printed
- Usernames are masked in debug output
- Netrc files should have restricted permissions
- Consider using environment variables in CI/automated environments