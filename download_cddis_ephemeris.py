#!/usr/bin/env python3
"""
NASA CDDIS GNSS Data Downloader

Downloads GPS RINEX V2 BRDC, RINEX V3 multi-GNSS , and IONEX files from CDDIS.
Includes fallback logic for IONEX types.
"""

import argparse
import gzip
import logging
import netrc
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configure logging
def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(levelname)s - %(message)s"

    # Get root logger and remove existing handlers to avoid duplicates
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Console handler
    logging.basicConfig(level=level, format=format_str)

    # Optional file handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(format_str))
        logging.getLogger().addHandler(file_handler)


def build_url_and_name(date: datetime, data_type: str) -> Tuple[str, str]:
    """
    Build CDDIS URL and filename for given date and data type.

    Args:
        date: Date to download
        data_type: The type of data file to download.

    Returns:
        Tuple of (url, filename)
    """
    year = date.year
    doy = date.timetuple().tm_yday  # Day of year
    yy = year % 100  # Two-digit year

    if data_type == "gps-v2":
        """         
        Daily RINEX V2 GPS Broadcast Ephemeris Files
        File Naming Convention:
        - Before Dec 1, 2020: YYYY/DDD/YYn/brdcDDD0.YYn.Z (compressed with .Z)
        - After Dec 1, 2020:  YYYY/DDD/YYn/brdcDDD0.YYn.gz (compressed with .gz)
        """
        # Check if date is after December 1, 2020
        cutoff_date = datetime(2020, 12, 1)

        if date >= cutoff_date:
            # Use .gz extension for dates after December 1, 2020
            filename = f"brdc{doy:03d}0.{yy:02d}n.gz"
        else:
            # Use .Z extension for dates before December 1, 2020
            filename = f"brdc{doy:03d}0.{yy:02d}n.Z"

        url = f"https://cddis.nasa.gov/archive/gnss/data/daily/{year}/{doy:03d}/{yy:02d}n/{filename}"
    elif data_type == "gnss-v3":
        # Daily RINEX V3 GNSS Broadcast Ephemeris Files (IGS Combined)
        # Note: These files are located in the /YYp/ subdirectory
        filename = f"BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"
        url = f"https://cddis.nasa.gov/archive/gnss/data/daily/{year}/{doy:03d}/{yy:02d}p/{filename}"
    elif data_type == "ionex-v1":
        # Old IONEX v1 format from IGS: igsgDDD0.YYi.Z
        filename = f"igsg{doy:03d}0.{yy:02d}i.Z"
        url = f"https://cddis.nasa.gov/archive/gnss/products/ionex/{year}/{doy:03d}/{filename}"
    elif data_type == "ionex-v2":
        # New IONEX format from IGS: IGS0OPSFIN_YYYYDDD0000_01D_02H_GIM.INX.gz
        filename = f"IGS0OPSFIN_{year}{doy:03d}0000_01D_02H_GIM.INX.gz"
        url = f"https://cddis.nasa.gov/archive/gnss/products/ionex/{year}/{doy:03d}/{filename}"
    else:
        raise ValueError(f"Unknown data type: {data_type}")

    return url, filename


def resolve_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve NASA Earthdata credentials from multiple sources.

    Returns:
        Tuple of (username, password) or (None, None) if not found
    """
    # 1. Environment variables first
    username = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if username and password:
        logging.debug("Using credentials from environment variables")
        return username, password

    # 2. Custom NETRC path
    netrc_path = os.environ.get("NETRC")
    if netrc_path:
        try:
            n = netrc.netrc(netrc_path)
            auth = n.authenticators("urs.earthdata.nasa.gov")
            if auth:
                logging.debug(f"Using credentials from NETRC: {netrc_path}")
                return auth[0], auth[2]
        except (FileNotFoundError, netrc.NetrcParseError) as e:
            logging.debug(f"Failed to read NETRC file {netrc_path}: {e}")

    # 3. Default netrc file locations
    home = os.path.expanduser("~")
    if os.name == 'nt':  # Windows
        netrc_file = Path(home) / "_netrc"
    else:  # POSIX
        netrc_file = Path(home) / ".netrc"

    try:
        n = netrc.netrc(str(netrc_file))
        auth = n.authenticators("urs.earthdata.nasa.gov")
        if auth:
            logging.debug(f"Using credentials from {netrc_file}")
            return auth[0], auth[2]
    except (FileNotFoundError, netrc.NetrcParseError) as e:
        logging.debug(f"Failed to read netrc file {netrc_file}: {e}")

    return None, None


def make_session(retries: int = 3, timeout: int = 60, proxy: Optional[str] = None) -> requests.Session:
    """
    Create a requests session with retry strategy and authentication.

    Args:
        retries: Number of retry attempts
        timeout: Request timeout in seconds
        proxy: Proxy URL (optional)

    Returns:
        Configured requests session
    """
    session = requests.Session()

    # Setup retry strategy
    retry_strategy = Retry(
        total=retries,
        status_forcelist=[429, 500, 502, 503, 504],
        backoff_factor=1,
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set timeout
    session.timeout = timeout

    # Configure proxy
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    elif os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY"):
        session.proxies = {
            "http": os.environ.get("HTTP_PROXY", ""),
            "https": os.environ.get("HTTPS_PROXY", "")
        }

    # Set credentials
    username, password = resolve_credentials()
    if username and password:
        session.auth = (username, password)
        logging.debug(f"Session configured with authentication for user: {username[:3]}***")
    else:
        raise ValueError("No valid credentials found")

    return session


def download_one(session: requests.Session, url: str, output_path: Path, skip_existing: bool = False) -> bool:
    """
    Download a single file from CDDIS.

    Args:
        session: Configured requests session
        url: URL to download
        output_path: Local path to save file
        skip_existing: Skip if file already exists

    Returns:
        True if successful, False if failed (but not fatal)
    """
    if skip_existing and output_path.exists():
        logging.info(f"Skipping existing file: {output_path}")
        return True

    try:
        logging.info(f"Downloading: {url}")
        response = session.get(url, stream=True)

        if response.status_code == 404:
            logging.warning(f"File not found (404): {url}")
            return False  # Non-fatal, allows fallback logic to trigger
        elif response.status_code in [401, 403]:
            logging.error(f"Authentication failed ({response.status_code}): {url}")
            logging.error("Check your NASA Earthdata credentials and ensure you've authorized CDDIS access")
            logging.error("Visit https://cddis.nasa.gov in a browser and sign in once with your Earthdata account")
            return False
        elif response.status_code != 200:
            logging.error(f"HTTP {response.status_code}: {url}")
            return False

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Download file
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        logging.info(f"Downloaded: {output_path} ({output_path.stat().st_size} bytes)")
        return True

    except requests.exceptions.SSLError as e:
        logging.error(f"SSL/TLS error: {e}")
        logging.error("Try setting REQUESTS_CA_BUNDLE environment variable to your corporate CA bundle")
        return False
    except requests.exceptions.ProxyError as e:
        logging.error(f"Proxy error: {e}")
        logging.error("Check HTTP_PROXY/HTTPS_PROXY environment variables")
        return False
    except Exception as e:
        logging.error(f"Download failed: {e}")
        return False


def decompress_gzip(gz_path: Path) -> bool:
    """
    Decompress a .gz file and remove the compressed version.

    Args:
        gz_path: Path to .gz file

    Returns:
        True if successful, False otherwise
    """
    if not str(gz_path).endswith(".gz"):
        logging.warning(f"File is not a standard .gz file: {gz_path}")
        return False

    # Handles extensions like .rnx.gz -> .rnx or .23i.gz -> .23i
    output_path = gz_path.with_suffix("")

    try:
        with gzip.open(gz_path, "rb") as f_in:
            with open(output_path, "wb") as f_out:
                f_out.write(f_in.read())

        # Remove compressed file
        gz_path.unlink()
        logging.info(f"Decompressed: {output_path}")
        return True

    except Exception as e:
        logging.warning(f"Decompression failed for {gz_path}: {e}")
        return False


def diagnose_environment() -> None:
    """Print diagnostic information about the environment."""
    print("=== Environment Diagnostics ===")
    print(f"Python executable: {sys.executable}")
    print(f"HOME: {os.environ.get('HOME', 'Not set')}")
    print(f"USERPROFILE: {os.environ.get('USERPROFILE', 'Not set')}")
    print(f"NETRC: {os.environ.get('NETRC', 'Not set')}")
    print(f"expanduser('~'): {os.path.expanduser('~')}")

    # Check netrc file
    netrc_path = os.environ.get("NETRC")
    if netrc_path:
        print(f"Custom netrc path: {netrc_path}")
        print(f"Custom netrc exists: {os.path.exists(netrc_path)}")

    home = os.path.expanduser("~")
    if os.name == 'nt':
        default_netrc = Path(home) / "_netrc"
    else:
        default_netrc = Path(home) / ".netrc"

    print(f"Default netrc path: {default_netrc}")
    print(f"Default netrc exists: {default_netrc.exists()}")

    # Check for URS entry (without revealing credentials)
    try:
        username, password = resolve_credentials()
        if username:
            print(f"URS entry found for user: {username[:3]}***")
        else:
            print("No URS entry found")
    except Exception as e:
        print(f"Credential check failed: {e}")

    # Environment variables
    print(f"EARTHDATA_USERNAME: {'Set' if os.environ.get('EARTHDATA_USERNAME') else 'Not set'}")
    print(f"EARTHDATA_PASSWORD: {'Set' if os.environ.get('EARTHDATA_PASSWORD') else 'Not set'}")
    print(f"HTTP_PROXY: {os.environ.get('HTTP_PROXY', 'Not set')}")
    print(f"HTTPS_PROXY: {os.environ.get('HTTPS_PROXY', 'Not set')}")
    print(f"REQUESTS_CA_BUNDLE: {os.environ.get('REQUESTS_CA_BUNDLE', 'Not set')}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download NASA CDDIS GNSS data (ephemeris and ionosphere)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single day GPS RINEX V2
  python download_cddis.py --date 2025-09-18 --type gps-v2

  # Date range GNSS RINEX V3 with decompression
  python download_cddis.py --start 2025-01-15 --end 2025-03-18 --type gnss-v3 --decompress

  # Date range for IONEX data (will try v2 if v1 fails, and vice versa)
  python download_cddis.py --start 2022-12-28 --end 2023-01-03 --type ionex-v1
        """
    )

    # Date specification (mutually exclusive)
    date_group = parser.add_mutually_exclusive_group(required=False)
    date_group.add_argument("--date", help="Single date (YYYY-MM-DD)")
    date_group.add_argument("--start", help="Start date for range (YYYY-MM-DD)")

    parser.add_argument("--end", help="End date for range (YYYY-MM-DD)")
    parser.add_argument("--type",
                        choices=["gps-v2", "gnss-v3", "ionex-v1", "ionex-v2"],
                        default="gps-v2",
                        help="Data type to download. For ionex types, will attempt fallback to other version if primary is not found.")
    parser.add_argument("--out", default=".", help="Output directory")
    parser.add_argument("--decompress", action="store_true",
                        help="Decompress .gz files after download")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip files that already exist")
    parser.add_argument("--retries", type=int, default=3,
                        help="Number of retry attempts")
    parser.add_argument("--timeout", type=int, default=60,
                        help="Request timeout in seconds")
    parser.add_argument("--proxy", help="Proxy URL")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")
    parser.add_argument("--diagnose", action="store_true",
                        help="Print environment diagnostics and exit")

    args = parser.parse_args()

    # Separate log files based on data type
    log_file = None
    if not args.diagnose:
        if 'ionex' in args.type:
            log_file = "logs/ionex_downloader.log"
        else:  # For 'gps-v2', 'gnss-v3'
            log_file = "logs/ephemeris_downloader.log"

    setup_logging(args.verbose, log_file)

    if args.diagnose:
        diagnose_environment()
        return 0

    # Validate date arguments
    if args.start and not args.end:
        parser.error("--end is required when --start is specified")
    if args.end and not args.start:
        parser.error("--start is required when --end is specified")
    if not args.date and not args.start:
        parser.error("Either --date or --start/--end must be specified")

    # Parse dates
    try:
        if args.date:
            start_date = end_date = datetime.strptime(args.date, "%Y-%m-%d")
        else:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
            end_date = datetime.strptime(args.end, "%Y-%m-%d")
    except ValueError as e:
        logging.error(f"Invalid date format: {e}")
        return 1

    if start_date > end_date:
        logging.error("Start date must be before or equal to end date")
        return 1

    # Check credentials early
    try:
        username, password = resolve_credentials()
        if not username or not password:
            logging.error("No valid NASA Earthdata credentials found!")
            logging.error("Checked locations:")
            logging.error("1. Environment variables: EARTHDATA_USERNAME, EARTHDATA_PASSWORD")
            netrc_path = os.environ.get("NETRC")
            if netrc_path:
                logging.error(f"2. Custom NETRC file: {netrc_path}")
            home = os.path.expanduser("~")
            if os.name == 'nt':
                default_netrc = Path(home) / "_netrc"
            else:
                default_netrc = Path(home) / ".netrc"
            logging.error(f"3. Default netrc file: {default_netrc}")
            logging.error("\nTo fix this, create a netrc file with:")
            logging.error("machine urs.earthdata.nasa.gov")
            logging.error("    login YOUR_USERNAME")
            logging.error("    password YOUR_PASSWORD")
            logging.error("\nOr set environment variables.")
            return 1
    except Exception as e:
        logging.error(f"Credential resolution failed: {e}")
        return 1

    # Create session
    try:
        session = make_session(args.retries, args.timeout, args.proxy)
    except Exception as e:
        logging.error(f"Failed to create session: {e}")
        return 1

    # Process date range
    current_date = start_date
    success_count = 0
    total_count = 0

    while current_date <= end_date:
        total_count += 1
        download_successful = False

        try:
            primary_type = args.type
            url, filename = build_url_and_name(current_date, primary_type)

            # --- Determine output subdirectory based on data type ---
            base_data_dir = Path(args.out) / "data"
            data_type_folder = "ionex" if 'ionex' in primary_type else "ephemeris"
            year_dir = base_data_dir / data_type_folder / str(current_date.year)
            file_path = year_dir / filename

            # --- Primary Download Attempt ---
            if download_one(session, url, file_path, args.skip_existing):
                download_successful = True
                if args.decompress and file_path.exists() and str(file_path).endswith(".gz"):
                    decompress_gzip(file_path)
            else:
                # --- Fallback Logic for IONEX types ---
                ionex_fallbacks = {"ionex-v1": "ionex-v2", "ionex-v2": "ionex-v1"}
                if primary_type in ionex_fallbacks:
                    fallback_type = ionex_fallbacks[primary_type]
                    logging.info(
                        f"'{primary_type}' not found for {current_date.date()}, trying fallback '{fallback_type}'")

                    # Build URL and path for the fallback attempt
                    fallback_url, fallback_filename = build_url_and_name(current_date, fallback_type)
                    fallback_file_path = year_dir / fallback_filename  # Use same directory

                    # Attempt fallback download
                    if download_one(session, fallback_url, fallback_file_path, args.skip_existing):
                        download_successful = True
                        if args.decompress and fallback_file_path.exists() and str(fallback_file_path).endswith(".gz"):
                            decompress_gzip(fallback_file_path)

            if download_successful:
                success_count += 1

        except Exception as e:
            logging.error(f"Failed to process {current_date.strftime('%Y-%m-%d')}: {e}")

        current_date += timedelta(days=1)

    logging.info(f"Completed: {success_count}/{total_count} files processed successfully")

    if success_count == 0 and total_count > 0:
        return 1  # All failed

    return 0


if __name__ == "__main__":
    sys.exit(main())