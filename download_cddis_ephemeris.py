#!/usr/bin/env python3
"""
NASA CDDIS GNSS Data Downloader

Downloads GPS RINEX V2 BRDC, RINEX V3 multi-GNSS, and IONEX files from CDDIS.
Automatically decompresses .gz and .Z files after download.
"""

import argparse
import gzip
import logging
import netrc
import os
import shutil
import subprocess
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

    if data_type == "rinex-v2-gps":
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
    elif data_type == "rinex-v3-gnss":
        """
        Daily RINEX V3 GNSS Broadcast Ephemeris Files (IGS Combined)
        """
        filename = f"BRDC00IGS_R_{year}{doy:03d}0000_01D_MN.rnx.gz"
        url = f"https://cddis.nasa.gov/archive/gnss/data/daily/{year}/{doy:03d}/{yy:02d}p/{filename}"
    elif data_type == "rinex-v4-gnss":
        """
        Daily RINEX V4 GNSS Broadcast Ephemeris Files
        """
        filename = f"BRD400DLR_S_{year}{doy:03d}0000_01D_MN.rnx.gz"
        url = f"https://cddis.nasa.gov/archive/gnss/data/daily/{year}/{doy:03d}/{yy:02d}p/{filename}"
    elif data_type == "ionex-v1":
        # Old IONEX v1 name format from IGS: igsgDDD0.YYi.Z
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

    # Also check if the decompressed version exists
    decompressed_path = output_path.with_suffix('')
    if skip_existing and decompressed_path.exists() and output_path.suffix in ['.gz', '.Z']:
        logging.info(f"Skipping download because decompressed file exists: {decompressed_path}")
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


def decompress_lzw_z_file(file_path: Path) -> bytes:
    """
    Decompress a .Z file using pure Python LZW implementation.

    Args:
        file_path: Path to the .Z compressed file

    Returns:
        Decompressed data as bytes

    Raises:
        ValueError: If file format is invalid
        Exception: If decompression fails
    """
    with open(file_path, "rb") as f:
        data = f.read()

    # Check magic number for .Z files
    if len(data) < 3 or data[:2] != b'\x1f\x9d':
        raise ValueError("Invalid .Z file format (missing magic number)")

    # Get compression parameters from third byte
    flags = data[2]
    max_bits = flags & 0x1f
    block_compress = (flags & 0x80) != 0

    if max_bits < 9 or max_bits > 16:
        raise ValueError(f"Invalid max_bits: {max_bits}")

    # Start decompression from byte 3 onwards
    compressed_data = data[3:]

    # Initialize LZW decompression
    clear_code = 256 if block_compress else -1
    code_size = 9
    max_code = (1 << code_size) - 1

    # Initialize dictionary
    dictionary = {}
    for i in range(256):
        dictionary[i] = bytes([i])

    next_code = 257 if block_compress else 256
    if block_compress:
        dictionary[256] = b''  # Clear code

    result = bytearray()
    bit_buffer = 0
    bit_count = 0
    pos = 0

    # Read first code
    while bit_count < code_size and pos < len(compressed_data):
        bit_buffer |= compressed_data[pos] << bit_count
        bit_count += 8
        pos += 1

    if bit_count < code_size:
        raise ValueError("Truncated data")

    old_code = bit_buffer & max_code
    bit_buffer >>= code_size
    bit_count -= code_size

    if old_code >= next_code:
        raise ValueError("Invalid initial code")

    if old_code == clear_code:
        # Handle clear code at start
        while bit_count < code_size and pos < len(compressed_data):
            bit_buffer |= compressed_data[pos] << bit_count
            bit_count += 8
            pos += 1

        if bit_count < code_size:
            raise ValueError("Truncated data after clear")

        old_code = bit_buffer & max_code
        bit_buffer >>= code_size
        bit_count -= code_size

    if old_code in dictionary:
        result.extend(dictionary[old_code])
    else:
        raise ValueError("Invalid code in stream")

    # Main decompression loop
    while pos < len(compressed_data) or bit_count >= code_size:
        # Read next code
        while bit_count < code_size and pos < len(compressed_data):
            bit_buffer |= compressed_data[pos] << bit_count
            bit_count += 8
            pos += 1

        if bit_count < code_size:
            break

        code = bit_buffer & max_code
        bit_buffer >>= code_size
        bit_count -= code_size

        if code == clear_code:
            # Reset dictionary
            dictionary = {}
            for i in range(256):
                dictionary[i] = bytes([i])
            dictionary[256] = b''
            next_code = 257
            code_size = 9
            max_code = (1 << code_size) - 1

            # Read next code after clear
            while bit_count < code_size and pos < len(compressed_data):
                bit_buffer |= compressed_data[pos] << bit_count
                bit_count += 8
                pos += 1

            if bit_count < code_size:
                break

            old_code = bit_buffer & max_code
            bit_buffer >>= code_size
            bit_count -= code_size

            if old_code in dictionary:
                result.extend(dictionary[old_code])
            continue

        if code in dictionary:
            # Code exists in dictionary
            string = dictionary[code]
            result.extend(string)

            # Add new entry to dictionary
            if next_code <= max_code:
                new_string = dictionary[old_code] + string[:1]
                dictionary[next_code] = new_string
                next_code += 1

                # Increase code size if needed
                if next_code > max_code and code_size < max_bits:
                    code_size += 1
                    max_code = (1 << code_size) - 1

        elif code == next_code:
            # Code doesn't exist yet, but should be the next one
            string = dictionary[old_code] + dictionary[old_code][:1]
            result.extend(string)
            dictionary[next_code] = string
            next_code += 1

            # Increase code size if needed
            if next_code > max_code and code_size < max_bits:
                code_size += 1
                max_code = (1 << code_size) - 1

        else:
            raise ValueError(f"Invalid code: {code}")

        old_code = code

    return bytes(result)


def decompress_file(file_path: Path) -> bool:
    """
    Decompress a .gz or .Z file and remove the original.

    Args:
        file_path: Path to the compressed file.

    Returns:
        True if successful, False otherwise.
    """
    suffix = file_path.suffix
    output_path = file_path.with_suffix("")

    if suffix == ".gz":
        try:
            with gzip.open(file_path, "rb") as f_in:
                with open(output_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            file_path.unlink()  # Remove original .gz file
            logging.info(f"Decompressed to: {output_path}")
            return True
        except Exception as e:
            logging.error(f"Failed to decompress .gz file {file_path}: {e}")
            return False

    elif suffix == ".Z":
        # Try Python-based LZW decompression first
        try:
            decompressed_data = decompress_lzw_z_file(file_path)
            with open(output_path, "wb") as f_out:
                f_out.write(decompressed_data)
            file_path.unlink()  # Remove original .Z file
            logging.info(f"Decompressed to: {output_path}")
            return True
        except Exception as e:
            logging.warning(f"Python LZW decompression failed: {e}, trying alternatives...")

        # Fallback to system uncompress command if available
        if shutil.which("uncompress"):
            try:
                subprocess.run(["uncompress", str(file_path)], check=True, capture_output=True)
                logging.info(f"Decompressed to: {output_path}")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logging.error(f"Failed to decompress .Z file with uncompress command: {e}")

        # Try using 7-zip if available (common on Windows)
        if shutil.which("7z"):
            try:
                subprocess.run(["7z", "x", str(file_path), f"-o{file_path.parent}"],
                               check=True, capture_output=True)
                file_path.unlink()  # Remove original .Z file
                logging.info(f"Decompressed to: {output_path}")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logging.error(f"Failed to decompress .Z file with 7-zip: {e}")

        # If all methods fail, leave the file compressed
        logging.warning(f"Could not decompress .Z file {file_path}. File left compressed.")
        logging.warning("To decompress .Z files, you can:")
        logging.warning("1. Install the 'lzw' Python package: pip install lzw")
        logging.warning("2. Install 7-zip and add it to your PATH")
        logging.warning("3. On Linux/WSL: install ncompress package")
        return False

    else:
        logging.debug(f"File {file_path} does not require decompression.")
        return True


def convert_ionex_to_bin(input_file: Path, date: datetime) -> bool:
    """
    Convert IONEX file to .bin format with standardized naming convention.

    Args:
        input_file: Path to the IONEX file
        date: Date object to determine day of year and year

    Returns:
        True if successful, False otherwise
    """
    if not input_file.exists():
        logging.error(f"Input file does not exist: {input_file}")
        return False

    # Get day of year and year for naming
    doy = date.timetuple().tm_yday  # Day of year (001-365/366)
    year = date.year

    # Create standardized bin filename: ionex0DDD_YYYY.bin
    bin_filename = f"ionex0{doy:03d}_{year}.bin"
    bin_output_path = input_file.parent / bin_filename

    try:
        # Copy file as-is to .bin format
        shutil.copyfile(input_file, bin_output_path)
        logging.info(f"Converted to BIN: {input_file.name} -> {bin_filename}")
        return True
    except Exception as e:
        logging.error(f"Failed to convert {input_file} to bin format: {e}")
        return False


def should_convert_to_bin(data_type: str) -> bool:
    """
    Check if the data type should be converted to bin format.

    Args:
        data_type: The data type string

    Returns:
        True if it's an IONEX type, False otherwise
    """
    return data_type in ["ionex-v1", "ionex-v2"]


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
    print(f"uncompress command available: {'Yes' if shutil.which('uncompress') else 'No'}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download and decompress NASA CDDIS GNSS data (ephemeris and ionosphere)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single day GPS RINEX V2
  python download_cddis.py --date 2025-09-18 --type rinex-v2-gps

  # Date range GNSS RINEX V3
  python download_cddis.py --start 2025-01-15 --end 2025-03-18 --type rinex-v3-gnss

  # Date range for IONEX data (will try v2 if v1 fails, and vice versa)
  python download_cddis.py --start 2022-12-28 --end 2023-01-03 --type ionex-v1

  # Download IONEX files and convert to bin format
  python download_cddis.py --date 2018-01-01 --type ionex-v1 --bin
        """
    )

    # Date specification (mutually exclusive)
    date_group = parser.add_mutually_exclusive_group(required=False)
    date_group.add_argument("--date", help="Single date (YYYY-MM-DD)")
    date_group.add_argument("--start", help="Start date for range (YYYY-MM-DD)")

    parser.add_argument("--end", help="End date for range (YYYY-MM-DD)")
    parser.add_argument("--type",
                        choices=["rinex-v2-gps", "rinex-v3-gnss", "rinex-v4-gnss", "ionex-v1", "ionex-v2"],
                        default="rinex-v2-gps",
                        help="Data type to download. For ionex types, will attempt fallback to other version if primary is not found.")
    parser.add_argument("--out", default=".", help="Output directory")
    parser.add_argument("--bin", action="store_true",
                        help="Convert IONEX files to standardized .bin format (ionex0DDD_YYYY.bin)")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip files that already exist (checks for compressed and decompressed versions)")
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
        else:
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
        final_file_path = None

        try:
            primary_type = args.type
            url, filename = build_url_and_name(current_date, primary_type)

            # --- Determine output subdirectory based on data type ---
            base_data_dir = Path(args.out) / "data"
            data_type_folder = "ionex" if 'ionex' in primary_type else "ephemeris"
            year_dir = base_data_dir / data_type_folder / str(current_date.year)
            file_path = year_dir / filename
            final_file_path = file_path

            # --- Primary Download Attempt ---
            if download_one(session, url, file_path, args.skip_existing):
                download_successful = True
            else:
                # --- Fallback Logic for IONEX types ---
                ionex_fallbacks = {"ionex-v1": "ionex-v2", "ionex-v2": "ionex-v1"}
                if primary_type in ionex_fallbacks:
                    fallback_type = ionex_fallbacks[primary_type]
                    logging.info(
                        f"'{primary_type}' not found for {current_date.date()}, trying fallback '{fallback_type}'")

                    fallback_url, fallback_filename = build_url_and_name(current_date, fallback_type)
                    fallback_file_path = year_dir / fallback_filename
                    final_file_path = fallback_file_path

                    if download_one(session, fallback_url, fallback_file_path, args.skip_existing):
                        download_successful = True

            if download_successful:
                success_count += 1
                if final_file_path and final_file_path.exists():
                    # Decompress the file
                    decompress_successful = decompress_file(final_file_path)

                    # Convert to bin if requested and it's an IONEX file
                    if args.bin and should_convert_to_bin(primary_type) and decompress_successful:
                        # Find the decompressed file
                        decompressed_file = final_file_path.with_suffix('')
                        if decompressed_file.exists():
                            convert_ionex_to_bin(decompressed_file, current_date)
                        else:
                            logging.warning(f"Decompressed file not found for bin conversion: {decompressed_file}")
                    elif args.bin and should_convert_to_bin(primary_type) and not decompress_successful:
                        # If decompression failed but we still have the original file, try to convert it
                        if final_file_path.exists():
                            logging.info("Decompression failed, attempting bin conversion of compressed file")
                            convert_ionex_to_bin(final_file_path, current_date)

        except Exception as e:
            logging.error(f"Failed to process {current_date.strftime('%Y-%m-%d')}: {e}")

        current_date += timedelta(days=1)

    logging.info(f"Completed: {success_count}/{total_count} files processed successfully")

    if success_count == 0 and total_count > 0:
        return 1  # All failed

    return 0


if __name__ == "__main__":
    sys.exit(main())