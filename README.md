# CDDIS Downloader Setup

## Prerequisites
- Python 3.7 or higher
- NASA Earthdata account credentials

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/cddis-downloader.git
   cd cddis-downloader
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   ```

3. **Activate virtual environment:**
   - Windows: `.venv\Scripts\activate.bat`
   - macOS/Linux: `source .venv/bin/activate`

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Setup NASA Earthdata credentials:**
   Create a `.netrc` file in your home directory:
   ```
   machine urs.earthdata.nasa.gov
       login YOUR_USERNAME
       password YOUR_PASSWORD
   ```

## Usage

### Windows (GUI):
Double-click `run_cddis_downloader.bat`

### Command Line:
```bash
python download_cddis_ephemeris.py --date 2025-09-18 --type gps-v2
```

## Examples
- Single day: `--date 2025-09-18 --type gps-v2`
- Date range: `--start 2025-01-01 --end 2025-01-07 --type gnss-v3 --decompress`
