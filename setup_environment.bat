@ECHO OFF
SETLOCAL EnableDelayedExpansion

:: ============================================================================
:: SimOR Environment Setup Script
:: ============================================================================
:: This script sets up the computing environment for the SimOR project.
:: It installs UV (if needed), clones and builds ActivitySim, optionally
:: installs the sandag_parking and activitysim_visualizer repos, and
:: configures Visum Python packages.
::
:: All cloned repos and virtual environments are placed in the
:: ext_dependencies subfolder within this SimOR repo.
:: ============================================================================

:: ---------------------------------------------------------------------------
:: User-configurable settings
:: ---------------------------------------------------------------------------
:: Set this to the folder containing Visum's bundled Python interpreter.
:: IMPORTANT: Do not include a trailing backslash at the end of this path.
:: Example: C:\Program Files\PTV Vision\PTV Visum 2026\Exe\Python
SET "VISUM_PYTHON_DIR=C:\Program Files\PTV Vision\PTV Visum 2026\Exe\Python"

:: Set to Y to clone and install sandag_parking, N to skip
:: (optional dependency, only needed if you want to regenerate parking cost data)
SET "INSTALL_PARKING=N"

:: Set to Y to clone and install the ActivitySim visualizer, N to skip
:: (optional dependency, only needed for producing model summary dashboards)
SET "INSTALL_VISUALIZER=Y"

:: ---------------------------------------------------------------------------
:: Repository URLs and branches
:: ---------------------------------------------------------------------------
SET "ACTIVITYSIM_REPO_URL=https://github.com/RSGInc/activitysim.git"
SET "ACTIVITYSIM_BRANCH=SimOR_pnr"

SET "PARKING_REPO_URL=https://github.com/RSGInc/sandag_parking.git"
SET "PARKING_BRANCH=oregon_metro"

SET "VISUALIZER_REPO_URL=https://github.com/RSGInc/activitysim_visualizer.git"
SET "VISUALIZER_BRANCH=main"
:: ---------------------------------------------------------------------------


:: ---------------------------------------------------------------------------
:: Resolve the base directory (the root of this SimOR repo)
:: ---------------------------------------------------------------------------
SET "BASE_DIR=%~dp0"
:: Remove trailing backslash
IF "%BASE_DIR:~-1%"=="\" SET "BASE_DIR=%BASE_DIR:~0,-1%"

ECHO ============================================================
ECHO  SimOR Environment Setup
ECHO ============================================================
ECHO.
ECHO  Base directory: %BASE_DIR%
ECHO.
ECHO  Repositories:
ECHO    ActivitySim  : %ACTIVITYSIM_REPO_URL% ^(branch: %ACTIVITYSIM_BRANCH%^)
ECHO    sandag_parking : %PARKING_REPO_URL% ^(branch: %PARKING_BRANCH%^) [install: %INSTALL_PARKING%]
ECHO    Visualizer   : %VISUALIZER_REPO_URL% ^(branch: %VISUALIZER_BRANCH%^) [install: %INSTALL_VISUALIZER%]
ECHO.

:: ---------------------------------------------------------------------------
:: Create ext_dependencies folder for cloned repos and environments
:: ---------------------------------------------------------------------------
SET "EXT_DIR=%BASE_DIR%\ext_dependencies"
IF NOT EXIST "%EXT_DIR%" (
    MKDIR "%EXT_DIR%"
    ECHO  Created ext_dependencies folder.
)


:: ============================================================================
:: STEP 1 – Ensure UV is installed
:: ============================================================================
ECHO [1/6] Checking for UV package manager...

where uv >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO  UV not found. Installing UV...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    IF !ERRORLEVEL! NEQ 0 (
        ECHO  ERROR: Failed to install UV.
        GOTO :ERROR_EXIT
    )
    :: Refresh PATH so uv is available in this session
    FOR /F "tokens=*" %%A IN ('powershell -Command "[System.Environment]::GetEnvironmentVariable('Path','User')"') DO SET "PATH=%%A;%PATH%"
    where uv >nul 2>&1
    IF !ERRORLEVEL! NEQ 0 (
        ECHO  ERROR: UV installed but not found on PATH. Please restart your terminal and re-run this script.
        GOTO :ERROR_EXIT
    )
    ECHO  UV installed successfully.
) ELSE (
    ECHO  UV is already installed.
)
ECHO.

:: ============================================================================
:: STEP 1b – Ensure Git is available
:: ============================================================================
ECHO  Checking for Git...
where git >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO  Git not found on PATH. Searching common install locations...
    SET "GIT_FOUND="
    FOR %%G IN (
        "%ProgramFiles%\Git\cmd"
        "%ProgramFiles(x86)%\Git\cmd"
        "%LOCALAPPDATA%\Programs\Git\cmd"
        "%ProgramFiles%\Git\bin"
    ) DO (
        IF EXIST "%%~G\git.exe" (
            SET "PATH=%%~G;!PATH!"
            SET "GIT_FOUND=1"
        )
    )
    IF NOT DEFINED GIT_FOUND (
        ECHO  ERROR: Git is not installed or not found.
        ECHO  Please install Git from https://git-scm.com/ and re-run this script.
        GOTO :ERROR_EXIT
    )
    ECHO  Found Git and added to PATH for this session.
) ELSE (
    ECHO  Git is available.
)
ECHO.

:: ============================================================================
:: STEP 2 – Clone / update ActivitySim and create its virtual environment
:: ============================================================================
ECHO [2/6] Setting up ActivitySim (%ACTIVITYSIM_BRANCH% branch)...

SET "ACTIVITYSIM_DIR=%EXT_DIR%\activitysim"

IF EXIST "%ACTIVITYSIM_DIR%\.git" (
    ECHO  ActivitySim repo already exists. Pulling latest changes...
    pushd "%ACTIVITYSIM_DIR%"
    git checkout %ACTIVITYSIM_BRANCH%
    git pull
    popd
) ELSE (
    ECHO  Cloning ActivitySim ^(%ACTIVITYSIM_BRANCH% branch^) from %ACTIVITYSIM_REPO_URL%...
    pushd "%EXT_DIR%"
    git clone --branch %ACTIVITYSIM_BRANCH% %ACTIVITYSIM_REPO_URL%
    IF !ERRORLEVEL! NEQ 0 (
        ECHO  ERROR: Failed to clone ActivitySim.
        popd
        GOTO :ERROR_EXIT
    )
    popd
)

:: Build the environment using the uv lock file
ECHO  Installing ActivitySim dependencies via UV...
pushd "%ACTIVITYSIM_DIR%"
uv sync --frozen --link-mode copy
IF !ERRORLEVEL! NEQ 0 (
    ECHO  ERROR: uv sync failed for ActivitySim.
    popd
    GOTO :ERROR_EXIT
)
uv pip install -e . --no-deps --link-mode copy
popd

:: Resolve the absolute path to the venv Python
FOR /F "delims=" %%P IN ('powershell -Command "(Resolve-Path '%ACTIVITYSIM_DIR%\.venv\Scripts\python.exe').Path"') DO SET "PYTHON_ACTIVITYSIM=%%P"

IF NOT EXIST "%PYTHON_ACTIVITYSIM%" (
    ECHO  ERROR: Could not find Python at %ACTIVITYSIM_DIR%\.venv\Scripts\python.exe
    GOTO :ERROR_EXIT
)

ECHO  PYTHON_ACTIVITYSIM = %PYTHON_ACTIVITYSIM%
ECHO.

:: ============================================================================
:: STEP 3 – Visum Python packages
:: ============================================================================
ECHO [3/6] Setting up Visum Python packages...

SET "VISUM_PACKAGE_STATUS=not checked"
SET "VISUM_PYTHON_EXE=%VISUM_PYTHON_DIR%\python.exe"

IF NOT EXIST "%VISUM_PYTHON_EXE%" (
    ECHO  WARNING: Visum Python not found at:
    ECHO    %VISUM_PYTHON_DIR%
    ECHO  Please edit VISUM_PYTHON_DIR in this script to point to your Visum 2026 Python folder.
    SET "VISUM_PACKAGE_STATUS=skipped (Visum Python not found)"
    GOTO :VISUM_DONE
)

:: Resolve site-packages path via temp file (handles spaces in paths)
SET "VISUM_SITE_PACKAGES="
SET "VISUM_SITE_FILE=%TEMP%\simor_visum_site_packages.txt"
"%VISUM_PYTHON_EXE%" -c "import sysconfig; print(sysconfig.get_paths().get('purelib',''))" > "%VISUM_SITE_FILE%" 2>nul
IF EXIST "%VISUM_SITE_FILE%" (
    SET /P VISUM_SITE_PACKAGES=<"%VISUM_SITE_FILE%"
    DEL /Q "%VISUM_SITE_FILE%" >nul 2>&1
)

IF NOT DEFINED VISUM_SITE_PACKAGES (
    ECHO  WARNING: Could not resolve Visum site-packages path.
    SET "VISUM_PACKAGE_STATUS=skipped (could not resolve site-packages)"
    GOTO :VISUM_DONE
)

ECHO  Resolved Visum site-packages path:
ECHO    !VISUM_SITE_PACKAGES!

:: Check if packages are already importable
SET "PYTHONNOUSERSITE=1"
"%VISUM_PYTHON_EXE%" -c "import tables,openmatrix,yaml,pandas,scipy; assert pandas.__version__.startswith('2.3'); assert scipy.__version__.startswith('1.16')" >nul 2>&1
IF !ERRORLEVEL! EQU 0 (
    ECHO  Required Visum packages are already available. Skipping install.
    SET "VISUM_PACKAGE_STATUS=already available"
    GOTO :VISUM_DONE
)

:: Ensure site-packages directory exists
IF NOT EXIST "!VISUM_SITE_PACKAGES!" (
    MKDIR "!VISUM_SITE_PACKAGES!" >nul 2>&1
    IF !ERRORLEVEL! NEQ 0 (
        ECHO  WARNING: Cannot create directory:
        ECHO    !VISUM_SITE_PACKAGES!
        ECHO  Re-run as Administrator or ask IT to install these packages.
        SET "VISUM_PACKAGE_STATUS=missing packages, no write access"
        GOTO :VISUM_DONE
    )
)

:: Test write access
>"!VISUM_SITE_PACKAGES!\.__simor_write_test__.tmp" ECHO write-test 2>nul
IF NOT EXIST "!VISUM_SITE_PACKAGES!\.__simor_write_test__.tmp" (
    ECHO  WARNING: Cannot write to:
    ECHO    !VISUM_SITE_PACKAGES!
    ECHO  Re-run as Administrator or ask IT to install these packages.
    SET "VISUM_PACKAGE_STATUS=missing packages, no write access"
    GOTO :VISUM_DONE
)
DEL /Q "!VISUM_SITE_PACKAGES!\.__simor_write_test__.tmp" >nul 2>&1

:: Install packages (--isolated avoids user-level config redirecting to user site-packages)
ECHO  Installing tables, openmatrix, pyyaml, pandas 2.3.x, and scipy 1.16.x into:
ECHO    !VISUM_SITE_PACKAGES!
"%VISUM_PYTHON_EXE%" -m pip install --isolated --upgrade tables openmatrix pyyaml pandas==2.3.* scipy==1.16.* --target "!VISUM_SITE_PACKAGES!"
IF !ERRORLEVEL! NEQ 0 (
    ECHO  WARNING: Failed to install one or more Visum Python packages.
    SET "VISUM_PACKAGE_STATUS=install failed"
) ELSE (
    ECHO  Visum packages installed successfully.
    SET "VISUM_PACKAGE_STATUS=installed/updated"
)

:VISUM_DONE
ECHO.

:: ============================================================================
:: STEP 4 – MAZ skimming Python environment
:: ============================================================================
ECHO [4/6] Setting up MAZ skimming Python environment...

SET "MAZ_SKIM_DIR=%EXT_DIR%\maz_skimming"

ECHO  Installing MAZ skimming dependencies via UV...
pushd "%MAZ_SKIM_DIR%"
uv sync --frozen --link-mode copy
IF !ERRORLEVEL! NEQ 0 (
    ECHO  ERROR: uv sync failed for MAZ skimming environment.
    popd
    GOTO :ERROR_EXIT
)
popd

:: Resolve the absolute path to the venv Python
FOR /F "delims=" %%P IN ('powershell -Command "(Resolve-Path '%MAZ_SKIM_DIR%\.venv\Scripts\python.exe').Path"') DO SET "PYTHON_MAZ_SKIMMING=%%P"

IF NOT EXIST "%PYTHON_MAZ_SKIMMING%" (
    ECHO  ERROR: Could not find Python at %MAZ_SKIM_DIR%\.venv\Scripts\python.exe
    GOTO :ERROR_EXIT
)

ECHO  PYTHON_MAZ_SKIMMING = %PYTHON_MAZ_SKIMMING%
ECHO.

:: ============================================================================
:: STEP 5 – (Optional) Clone / update sandag_parking
:: ============================================================================

ECHO [5/6] Setting up sandag_parking...

IF /I "%INSTALL_PARKING%"=="Y" (
    ECHO  Setting up sandag_parking ^(%PARKING_BRANCH% branch^)...

    SET "PARKING_DIR=%EXT_DIR%\sandag_parking"

    IF EXIST "!PARKING_DIR!\.git" (
        ECHO  sandag_parking repo already exists. Pulling latest changes...
        pushd "!PARKING_DIR!"
        git checkout %PARKING_BRANCH%
        git pull
        popd
    ) ELSE (
        ECHO  Cloning sandag_parking ^(%PARKING_BRANCH% branch^) from %PARKING_REPO_URL%...
        pushd "%EXT_DIR%"
        git clone --branch %PARKING_BRANCH% %PARKING_REPO_URL%
        IF !ERRORLEVEL! NEQ 0 (
            ECHO  ERROR: Failed to clone sandag_parking.
            popd
            GOTO :ERROR_EXIT
        )
        popd
    )

    :: Build the environment using the uv lock file
    ECHO  Installing sandag_parking dependencies via UV...
    pushd "!PARKING_DIR!"
    uv sync --frozen --link-mode copy
    IF !ERRORLEVEL! NEQ 0 (
        ECHO  ERROR: uv sync failed for sandag_parking.
        popd
        GOTO :ERROR_EXIT
    )
    popd

    :: Resolve the absolute path to the venv Python
    FOR /F "delims=" %%P IN ('powershell -Command "(Resolve-Path '!PARKING_DIR!\.venv\Scripts\python.exe').Path"') DO SET "PYTHON_PARKING=%%P"

    IF NOT EXIST "!PYTHON_PARKING!" (
        ECHO  ERROR: Could not find Python at !PARKING_DIR!\.venv\Scripts\python.exe
        GOTO :ERROR_EXIT
    )

    ECHO  PYTHON_PARKING = !PYTHON_PARKING!
) ELSE (
    :: Even if not cloning, set the variable if the repo already exists
    SET "PARKING_DIR=%EXT_DIR%\sandag_parking"
    IF EXIST "!PARKING_DIR!\.venv\Scripts\python.exe" (
        FOR /F "delims=" %%P IN ('powershell -Command "(Resolve-Path '!PARKING_DIR!\.venv\Scripts\python.exe').Path"') DO SET "PYTHON_PARKING=%%P"
        ECHO  Existing sandag_parking environment found.
        ECHO  PYTHON_PARKING = !PYTHON_PARKING!
    ) ELSE (
        SET "PYTHON_PARKING="
        ECHO  sandag_parking skipped.
    )
)
ECHO.

:: ============================================================================
:: STEP 6 – (Optional) Clone / update the ActivitySim visualizer
:: ============================================================================
ECHO [6/6] Setting up ActivitySim visualizer...

SET "VISUALIZER_DIR=%EXT_DIR%\activitysim_visualizer"

IF /I "%INSTALL_VISUALIZER%"=="Y" (
    ECHO  Setting up activitysim_visualizer ^(%VISUALIZER_BRANCH% branch^)...

    IF EXIST "!VISUALIZER_DIR!\.git" (
        ECHO  activitysim_visualizer repo already exists. Pulling latest changes...
        pushd "!VISUALIZER_DIR!"
        git checkout %VISUALIZER_BRANCH%
        git pull
        popd
    ) ELSE (
        ECHO  Cloning activitysim_visualizer ^(%VISUALIZER_BRANCH% branch^) from %VISUALIZER_REPO_URL%...
        pushd "%EXT_DIR%"
        git clone --branch %VISUALIZER_BRANCH% %VISUALIZER_REPO_URL%
        IF !ERRORLEVEL! NEQ 0 (
            ECHO  ERROR: Failed to clone activitysim_visualizer.
            popd
            GOTO :ERROR_EXIT
        )
        popd
    )

    ECHO  Installing activitysim_visualizer dependencies via UV...
    pushd "!VISUALIZER_DIR!"
    uv sync --link-mode copy
    IF !ERRORLEVEL! NEQ 0 (
        ECHO  ERROR: uv sync failed for activitysim_visualizer.
        popd
        GOTO :ERROR_EXIT
    )
    popd

    FOR /F "delims=" %%P IN ('powershell -Command "(Resolve-Path '!VISUALIZER_DIR!\.venv\Scripts\python.exe').Path"') DO SET "PYTHON_VISUALIZER=%%P"

    IF NOT EXIST "!PYTHON_VISUALIZER!" (
        ECHO  ERROR: Could not find Python at !VISUALIZER_DIR!\.venv\Scripts\python.exe
        GOTO :ERROR_EXIT
    )

    ECHO  PYTHON_VISUALIZER = !PYTHON_VISUALIZER!
) ELSE (
    :: Even if not cloning, set the variable if the repo already exists
    IF EXIST "!VISUALIZER_DIR!\.venv\Scripts\python.exe" (
        FOR /F "delims=" %%P IN ('powershell -Command "(Resolve-Path '!VISUALIZER_DIR!\.venv\Scripts\python.exe').Path"') DO SET "PYTHON_VISUALIZER=%%P"
        ECHO  Existing activitysim_visualizer environment found.
        ECHO  PYTHON_VISUALIZER = !PYTHON_VISUALIZER!
    ) ELSE (
        SET "PYTHON_VISUALIZER="
        ECHO  activitysim_visualizer skipped.
    )
)
ECHO.

:: Set PYTHON_VISUM as the full path to the Visum Python executable
IF EXIST "%VISUM_PYTHON_DIR%\python.exe" (
    SET "PYTHON_VISUM=%VISUM_PYTHON_DIR%\python.exe"
) ELSE (
    SET "PYTHON_VISUM="
)

:: ============================================================================
:: Summary
:: ============================================================================
ECHO ============================================================
ECHO  Environment Setup Complete
ECHO ============================================================
ECHO.
ECHO  PYTHON_ACTIVITYSIM  = %PYTHON_ACTIVITYSIM%
ECHO  PYTHON_MAZ_SKIMMING = %PYTHON_MAZ_SKIMMING%
ECHO  PYTHON_VISUM        = %PYTHON_VISUM%
ECHO  VISUM_PACKAGES      = %VISUM_PACKAGE_STATUS%
IF DEFINED PYTHON_PARKING (
    ECHO  PYTHON_PARKING      = !PYTHON_PARKING!
) ELSE (
    ECHO  PYTHON_PARKING      = ^(not set^)
)
IF DEFINED PYTHON_VISUALIZER (
    ECHO  PYTHON_VISUALIZER   = !PYTHON_VISUALIZER!
) ELSE (
    ECHO  PYTHON_VISUALIZER   = ^(not set^)
)
ECHO.
ECHO ============================================================

:: ---------------------------------------------------------------------------
:: Export variables to the caller's scope (survives ENDLOCAL)
:: ---------------------------------------------------------------------------
ENDLOCAL & (
    SET "PYTHON_ACTIVITYSIM=%PYTHON_ACTIVITYSIM%"
    SET "PYTHON_MAZ_SKIMMING=%PYTHON_MAZ_SKIMMING%"
    SET "PYTHON_VISUM=%PYTHON_VISUM%"
    SET "PYTHON_PARKING=%PYTHON_PARKING%"
    SET "PYTHON_VISUALIZER=%PYTHON_VISUALIZER%"
    SET "VISUM_PACKAGE_STATUS=%VISUM_PACKAGE_STATUS%"
    SET "EXT_DIR=%EXT_DIR%"
    SET "BASE_DIR=%BASE_DIR%"
    SET "PATH=%PATH%"
)
GOTO :EOF

:ERROR_EXIT
ECHO.
ECHO ============================================================
ECHO  Setup failed. See errors above.
ECHO ============================================================
ENDLOCAL
EXIT /B 1
