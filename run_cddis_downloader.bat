@echo off
title CDDIS Downloader - NASA GNSS Data Tool
color 0F
mode con cols=100 lines=40

:startup
cls
echo.
echo  ====================================================================================
echo  =                           CDDIS DOWNLOADER v1.1                                 =
echo  =                     NASA GNSS Data Acquisition Tool                             =
echo  ====================================================================================
echo.
echo  Current Directory: %CD%
echo.

echo  Initializing virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo  ERROR: Failed to activate virtual environment
    echo  Please ensure .venv folder exists and is properly configured
    pause
    exit /b 1
)
echo  Virtual environment activated successfully!
echo.

echo  Checking dependencies...
python -c "import requests; print('  Dependencies verified!')" 2>nul
if errorlevel 1 (
    echo  Installing dependencies from requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo  ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
    echo  Dependencies installed successfully!
)
echo.

echo  CDDIS Downloader is ready!
echo.

:main_menu
echo  ====================================================================================
echo  =                                  MAIN MENU                                      =
echo  ====================================================================================
echo.
echo  Available Commands:
echo    * Type your download arguments directly
echo    * 'help' 	- Show detailed help and examples
echo    * 'clear'       - Clear the screen
echo    * 'exit'        - Quit the program
echo.

:input_loop
echo  ________________________________________________________________________________
set /p "user_args=  CDDIS> "
echo  ________________________________________________________________________________

if /i "%user_args%"=="exit" goto end
if /i "%user_args%"=="help" goto show_help
if /i "%user_args%"=="--help" goto show_help
if /i "%user_args%"=="clear" goto clear_screen


if "%user_args%"=="" (
    echo  WARNING: Please enter some arguments, 'help' for examples, or 'exit' to quit
    echo.
    goto input_loop
)

echo.
echo  ====================================================================================
echo  =                                  EXECUTING                                       =
echo  ====================================================================================
echo  Running: python download_cddis_ephemeris.py %user_args%
echo  ------------------------------------------------------------------------------------
python download_cddis_ephemeris.py %user_args%
echo  ------------------------------------------------------------------------------------
echo  Script execution completed
echo.
goto input_loop

:show_help
cls
echo.
echo  ====================================================================================
echo  =                              CDDIS DOWNLOADER HELP                              =
echo  ====================================================================================
echo.
echo  PURPOSE:
echo    Download GNSS data files from NASA's CDDIS archive including:
echo    * GPS/GNSS broadcast ephemeris files (RINEX format)
echo    * Ionospheric data (IONEX format)
echo.
echo  DATA TYPES:
echo    * rinex-v2-gps  - RINEX V2 GPS Broadcast Ephemeris (legacy format)
echo    * rinex-v3-gnss - RINEX V3 Multi-GNSS Broadcast Ephemeris (modern format)
echo    * rinex-v4-gnss - RINEX V4 Multi-GNSS Broadcast Ephemeris (latest format)
echo    * ionex-v1      - IONEX V1 format (older ionospheric data)
echo    * ionex-v2      - IONEX V2 format (newer ionospheric data)
echo.
echo  BASIC SYNTAX:
echo    --date YYYY-MM-DD --type [DATA_TYPE]              (Single day)
echo    --start YYYY-MM-DD --end YYYY-MM-DD --type [TYPE]  (Date range)
echo.
echo  ADDITIONAL OPTIONS:
echo    --decompress     - Automatically decompress downloaded .gz/.Z files
echo    --skip-existing  - Skip files that already exist locally
echo    --out [PATH]     - Specify output directory (default: current directory)
echo    --verbose        - Enable detailed logging
echo    --diagnose       - Show environment diagnostics
echo.
echo  PRACTICAL EXAMPLES:
echo.
echo    Single Day Examples:
echo      --date 2025-09-18 --type rinex-v2-gps
echo      --date 2024-12-25 --type rinex-v3-gnss --decompress
echo      --date 2023-06-15 --type rinex-v4-gnss --out ./data
echo      --date 2025-01-15 --type ionex-v1 --decompress
echo      --date 2025-01-15 --type ionex-v2 --out ./ionex
echo.
echo    Date Range Examples:
echo      --start 2025-01-01 --end 2025-01-07 --type rinex-v2-gps --decompress
echo      --start 2024-12-20 --end 2024-12-31 --type rinex-v3-gnss --skip-existing
echo      --start 2023-01-01 --end 2023-01-05 --type rinex-v4-gnss --out ./ephemeris
echo.
echo    Advanced Examples:
echo      --date 2025-09-18 --type rinex-v2-gps --out ./ephemeris --verbose --decompress
echo      --start 2024-01-01 --end 2024-01-05 --type ionex-v2 --skip-existing --out ./ionex
echo.
echo  DATA AVAILABILITY AND FORMATS:
echo    * RINEX V2 GPS: Available from ~1994 onwards
echo      - Before Dec 1, 2020: Uses .Z compression (Unix compress)
echo      - After Dec 1, 2020: Uses .gz compression (gzip)
echo    * RINEX V3 GNSS: Available from ~2010 onwards (always .gz)
echo    * RINEX V4 GNSS: Available from ~2022 onwards (always .gz)
echo    * IONEX V1: Available from ~1998-2022 (uses .Z compression)
echo    * IONEX V2: Available from ~2022 onwards (uses .gz compression)
echo.
echo  IMPORTANT NOTES:
echo    * Requires NASA Earthdata account credentials
echo    * Files may not be available for very recent dates (1-3 days delay)
echo    * Large date ranges may take considerable time to download
echo    * RINEX V2 uses different compression formats before/after Dec 1, 2020
echo    * RINEX V4 and IONEX V2 are newer formats with limited historical data
echo.
pause
goto clear_screen

:clear_screen
cls
goto main_menu

:end
echo.
echo  ===================================================================================
echo  =                                 PROGRAM CLOSED!                                 =
echo  ===================================================================================
echo.
echo  Press any key to close...
pause >nul
exit /b 0