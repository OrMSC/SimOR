# SimOR
Simulate Oregon (SimOR) - Oregon's Jointly Estimated ActivitySim Model
![image](SimOR.png)

> [!WARNING]
> This model is under active development, and the following instructions are subject to change.

Please see this repo's Wiki page for more detailed information on this model.

## Repository structure

The repository is organized into the following major components:

| Path | Purpose |
|------|---------|
| `runSIMOR.bat` | Top-level batch script that runs environment setup, skimming, preprocessing, and the current ActivitySim example run |
| `setup_environment.bat` | Installs UV if needed, clones and updates external dependencies, creates Python environments, and installs required Visum Python packages |
| `ext_dependencies/` | Cloned external repositories and their virtual environments, including ActivitySim, maz_skimming, and optionally sandag_parking |
| `resident/` | ActivitySim model code, configurations, test cases, model input data, and outputs |
| `resident/configs/` | Shared ActivitySim settings used across regions |
| `resident/configs_*` | Region-specific ActivitySim settings, constants, and overrides such as `configs_skats`; additional region folders such as `configs_metro` or `configs_lcog` may be added over time |
| `resident/model_data/` | Region-specific model inputs, including cropped example datasets and full datasets |
| `skimming_and_assignment/visum/` | Visum runner scripts, procedure sequences, and version files used to build motorized skims and export network inputs |
| `skimming_and_assignment/maz_maz_stop_skims/` | Non-motorized skim preprocessor and skim settings |
| `misc/` | Miscellaneous analysis and support scripts |

## Running the model

### Prerequisites

Before running the model, make sure the following are available:

1. PTV Visum 2026 with its bundled Python installation
2. Git available on your system PATH or installed in a standard Windows location
3. PowerShell with permission to run the UV installer invoked by `setup_environment.bat`
4. Local write access to the Visum Python `site-packages` directory, or Administrator privileges if package installation there is restricted

### Setup

1. **Configure `setup_environment.bat`**

   Open `setup_environment.bat` and set the user-configurable variables at the top of the file:

   | Variable | Description | Default |
   |----------|-------------|---------|
   | `VISUM_PYTHON_DIR` | Folder containing your Visum 2026 Python interpreter | `C:\Program Files\PTV Vision\PTV Visum 2026\Exe\Python` |
   | `INSTALL_PARKING` | Clone and install sandag_parking (`Y` or `N`) | `N` |

   You can run this script on its own to install all dependencies without running the model:
   ```
   setup_environment.bat
   ```
   It will install UV (if needed), verify Git is available, clone and build the required repositories into `ext_dependencies/`, create the ActivitySim and MAZ skimming Python environments, and install the necessary Python packages into Visum's Python environment. On subsequent runs it detects existing installs and pulls the latest changes instead of re-cloning.

   `sandag_parking` is not required for a typical model run. It is only needed when preparing land use inputs that require expected parking costs. In that workflow, it can be run once to generate the parking cost input file used by the preprocessor.

   **If permissions errors arise, try running the setup with Administrator privileges. The Visum Python package install in particular may require elevated permissions.**

2. **Place the Visum version file**

   Copy your Visum network version file (`.ver`) into `skimming_and_assignment/visum/`.

3. **Update configuration files**

   Edit the following files to match your local data paths, region, and project settings:

   | File | Purpose |
   |------|---------|
   | `skimming_and_assignment/maz_maz_stop_skims/2zoneSkim_params.yaml` | Non-motorized skim settings, Visum export locations, network inputs, and skim outputs |
   | `resident/preprocessor_settings.yaml` | Land use preprocessor input/output paths, network shapefiles, skim inputs, and optional parking or fare inputs |

   At minimum, confirm that these files point to the correct local locations for:

   1. Household, person, and land use CSV inputs
   2. MAZ, node, and link shapefiles
   3. Non-motorized skim inputs and outputs
   4. Optional expected parking cost and transit fare inputs

4. **Set user-defined variables in `runSIMOR.bat`**

   Open `runSIMOR.bat` and update the following variables at the top of the file:

   | Variable | Description |
   |----------|-------------|
   | `VISUM_VERSION_FILE` | Filename of the Visum version file |
   | `PROCEDURE_SEQ` | Path to the Visum procedure sequence XML |
   | `VISUM_PED_VERSION_FILE` | Optional pedestrian network Visum version file used when a separate pedestrian export is needed |
   | `PED_PROCEDURE_SEQ` | Optional Visum procedure sequence for the pedestrian network export |

### ActivitySim configuration layout

ActivitySim settings are split into a shared configuration folder and optional region-specific configuration folders.

- `resident/configs/` contains shared settings used across model regions.
- Region-specific folders such as `resident/configs_skats/`, and future folders such as `resident/configs_metro/` or `resident/configs_lcog/`, contain region-specific constants and overrides.
- When running a region-specific model, pass the region-specific config directory first and then the shared config directory so region overrides are applied before shared settings.

For example:

```bat
python resident\simulation.py -c resident\configs_skats -c resident\configs -d resident\model_data\skats\data_cropped -o resident\outputs\test
```

### Running the Pipeline

Run:
```
runSIMOR.bat
```

The script automatically calls `setup_environment.bat` to ensure all dependencies are installed and Python paths are set, then runs the following steps in sequence:

1. **Motorized skims** — Using Visum `Visum_Runner.py`. Automatically outputs required files to run non-motorized skims.
2. **Non-motorized skim preprocessor** — Prepares walk network inputs via `2zoneSkim_preprocessor.py`.
3. **Non-motorized skims** — Computes MAZ-to-MAZ and MAZ-to-stop walk skims via `2zoneSkim.py`.
4. **Land use preprocessor** — Builds ActivitySim-ready land use table via `preprocessor.py`.
5. **Run ActivitySim** — Runs the current ActivitySim example configured in `runSIMOR.bat`.

At present, the ActivitySim command in `runSIMOR.bat` runs the Metro cropped example dataset:

```bat
python resident\simulation.py -c resident\configs -d resident\model_data\metro\data_cropped -o outputs\cropped
```

This is a smoke-test style example run, not yet a generalized full-region launcher for all supported scenarios.

### Expected inputs and outputs

- Visum produces the motorized skims and exported network files consumed by the non-motorized skim workflow.
- The non-motorized skim tools produce files such as `maz_maz_walk.csv` and `maz_stop_walk.csv` for use by the land use preprocessor and ActivitySim.
- The land use preprocessor reads the configured raw model inputs and writes updated ActivitySim-ready tables to the configured output directory.
- ActivitySim writes model outputs to the output folder passed on the command line.