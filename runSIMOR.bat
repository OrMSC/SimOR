@ECHO OFF
SETLOCAL

::~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:: Run ActivitySim and associated scripts
::~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:: ---------------------------------------------------------------------------
:: Settings
:: ---------------------------------------------------------------------------
SET "BASE_DIR=%~dp0"
IF "%BASE_DIR:~-1%"=="\" SET "BASE_DIR=%BASE_DIR:~0,-1%"
SET "SKIM_DIR=%BASE_DIR%\skimming_and_assignment"
SET "MODEL_DIR=%BASE_DIR%\resident"

:: User-defined Visum version file and procedure sequence
SET "VISUM_VERSION_FILE=Metro_Model_v1_AllStreetsNetwork_MasterTransit_Visum26.ver"
SET "PROCEDURE_SEQ=%SKIM_DIR%\visum\config\visum_metro\SkimSequence_Metro.xml"

:: If separate pedestrian network provided, specify here. Leave empty otherwise.
@REM SET "VISUM_PED_VERSION_FILE=OSM_LCOG_DKS_v7.ver"
@REM SET "PED_PROCEDURE_SEQ=%SKIM_DIR%\visum\config\visum_lcog\SkimSequence_AllStreets_Export.xml"
SET "VISUM_PED_VERSION_FILE="
SET "PED_PROCEDURE_SEQ="

:: ---------------------------------------------------------------------------
:: Run environment setup (installs dependencies & exports Python paths)
:: ---------------------------------------------------------------------------
ECHO Running environment setup...
CALL "%BASE_DIR%\setup_environment.bat"
IF %ERRORLEVEL% NEQ 0 (
    ECHO Environment setup failed. Aborting.
    EXIT /B 1
)

ECHO.
ECHO Base directory: %BASE_DIR%
ECHO Model directory: %MODEL_DIR%
ECHO Skimming directory: %SKIM_DIR%
ECHO.
 
:: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:: Skimming
:: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:: Run motorized skims in Visum
ECHO.
ECHO Running motorized skims.
ECHO Visum version file: %VISUM_VERSION_FILE%
ECHO Procedure sequence: %PROCEDURE_SEQ%

CD /D "%SKIM_DIR%\visum"
"%PYTHON_VISUM%" Visum_Runner.py "%VISUM_VERSION_FILE%" "%PROCEDURE_SEQ%"
IF %ERRORLEVEL% NEQ 0 GOTO MODEL_ERROR
ECHO Motorized skims complete.

IF DEFINED VISUM_PED_VERSION_FILE (
    ECHO.
    ECHO Exporting pedestrian network from: %VISUM_PED_VERSION_FILE%
    CD /D "%SKIM_DIR%\visum"
    "%PYTHON_VISUM%" Visum_Runner.py "%VISUM_PED_VERSION_FILE%" "%PED_PROCEDURE_SEQ%"
    IF %ERRORLEVEL% NEQ 0 GOTO MODEL_ERROR
    ECHO Pedestrian network exported.
)

:: Run non-motorized skims in Python
ECHO.
ECHO Running non-motorized skim preprocessor.
CD /D "%SKIM_DIR%\maz_maz_stop_skims"
"%PYTHON_MAZ_SKIMMING%" 2zoneSkim_preprocessor.py 2zoneSkim_params.yaml
IF %ERRORLEVEL% NEQ 0 GOTO MODEL_ERROR

ECHO.
ECHO Running non-motorized skims. 
"%PYTHON_MAZ_SKIMMING%" 2zoneSkim.py 2zoneSkim_params.yaml
IF %ERRORLEVEL% NEQ 0 GOTO MODEL_ERROR
ECHO Non-motorized skims complete.

:: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:: Run ActivitySim -- full integration not yet implemented. This will only run the small cropped metro example dataset.
:: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ECHO.
ECHO Running ActivitySim preprocessor.
CD /D "%MODEL_DIR%"
"%PYTHON_ACTIVITYSIM%" preprocessor.py preprocessor_settings.yaml
IF %ERRORLEVEL% NEQ 0 GOTO MODEL_ERROR
ECHO ActivitySim preprocessor complete.

ECHO.
ECHO Running ActivitySim (test cropped example)
"%PYTHON_ACTIVITYSIM%" resident\simulation.py -c resident\configs -d resident\model_data\metro\data_cropped -o outputs\cropped
IF %ERRORLEVEL% NEQ 0 GOTO MODEL_ERROR
ECHO ActivitySim complete.

:: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
:: Run the ActivitySim visualizer (optional)
:: ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SET "VISUALIZER_DIR=%BASE_DIR%\ext_dependencies\activitysim_visualizer"

IF NOT DEFINED PYTHON_VISUALIZER (
    ECHO.
    ECHO Visualizer environment not set up. Skipping visualizer step.
) ELSE (
    ECHO.
    ECHO Running ActivitySim visualizer.
    CD /D "%BASE_DIR%"
    "%PYTHON_VISUALIZER%" "%VISUALIZER_DIR%\run.py" --config resident/configs_visualizer/metro_cropped.yaml --export-html metro_cropped.html
    IF ERRORLEVEL 1 GOTO MODEL_ERROR
    ECHO Visualizer complete.
)

ECHO.
ECHO All steps completed successfully.
ENDLOCAL
GOTO :EOF

:MODEL_ERROR
ECHO.
ECHO ERROR: A step failed. Check the output above for details.
ENDLOCAL
EXIT /B 1