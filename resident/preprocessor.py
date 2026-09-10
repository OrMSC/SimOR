"""
Preprocessor for ActivitySim input files.
Adds derived columns to land_use, households, and persons tables.
"""

import pandas as pd
import numpy as np
import geopandas as gpd
import openmatrix as omx
import numpy as np
import sys
import os
import time
import yaml
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PreprocessorSettings:
    """Settings for the preprocessor."""
    data_dir: Path = field(default_factory=lambda: Path("data"))
    output_dir: Path = None  # None means overwrite input files
    households_file: str = "households.csv"
    persons_file: str = "persons.csv"
    land_use_file: str = "land_use.csv"
    maz_shp_file: str = None  # Path to MAZ shapefile for calculating acres
    maz_stop_walk_file: str = None  # Path to MAZ stop walk distances file
    fare_skim_input_file: str = None  # Path to non-TOD segmented fare skim matrix file
    times_of_day: list[str] = field(default_factory=lambda: ["EA", "AM", "MD", "PM", "EV"])
    transit_fare_system: dict = None
    maz_maz_walk_file: str = None
    nodes_file: str = None
    links_file: str = None
    density_radius: float = 0.50 # Buffer radius for density calcs, miles 
    link_filter_col: str = None
    keep_link_types: dict = None
    count_intersections: bool = True
    icnt_col: str = None
    exp_parking_costs_file: str = None
    
    def __post_init__(self):
        # Convert strings to Path objects
        if isinstance(self.data_dir, str):
            self.data_dir = Path(self.data_dir)
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        
        # Check intersection count field is provided if not counting inters 
        if not self.count_intersections and not self.icnt_col:
            raise ValueError(
                "intersection column must be provided when count_intersections is False"
            )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "PreprocessorSettings":
        """Load settings from a YAML file."""
        with open(yaml_path, "r") as f:
            config = yaml.safe_load(f) or {}
        return cls(**config)


def load_data(settings: PreprocessorSettings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the three input CSV files."""
    households = pd.read_csv(settings.data_dir / settings.households_file)
    persons = pd.read_csv(settings.data_dir / settings.persons_file)
    land_use = pd.read_csv(settings.data_dir / settings.land_use_file)
    land_use = land_use.rename(
        columns = {
            'ENROLLGRADEKTO8': 'ENROLLGRADEKto8',
            'ENROLLGRADE9TO12': 'ENROLLGRADE9to12'
        })
    return households, persons, land_use


def set_land_use_maz_index(land_use: pd.DataFrame) -> pd.DataFrame:
    """Infer the MAZ and TAZ columns, rename them, and set MAZ as the index.
    
    Searches for common MAZ column name variations (MAZ, MAZ_ID, MAZ_NO)
    and TAZ column name variations (TAZ, TAZ_ID, TAZ_NO), standardizes
    their names to 'MAZ' and 'TAZ', and sets 'MAZ' as the DataFrame index.
    
    Parameters
    ----------
    land_use : pd.DataFrame
        Land use table with MAZ-like and optionally TAZ-like columns
        
    Returns
    -------
    pd.DataFrame
        Land use table with 'MAZ' as the index and 'TAZ' column renamed
    """
    # --- MAZ ---
    # If MAZ is already the index, just ensure the name
    if land_use.index.name and land_use.index.name == 'MAZ':
        land_use.index.name = 'MAZ'
        print("land_use index already set to MAZ")
    else:
        # Search for a MAZ-like column
        maz_col = None
        for col in land_use.columns:
            if col.upper() in ['MAZ', 'MAZ_ID', 'MAZ_NO']:
                maz_col = col
                break
        
        if maz_col is None:
            raise RuntimeError(
                f"Could not identify MAZ column in land_use. "
                f"Available columns: {list(land_use.columns)}"
            )
        
        # Rename to 'MAZ' if needed, then set as index
        if maz_col != 'MAZ':
            land_use = land_use.rename(columns={maz_col: 'MAZ'})
            print(f"Renamed land_use column '{maz_col}' to 'MAZ'")
        
        land_use = land_use.set_index('MAZ')
        print(f"Set land_use index to 'MAZ' ({len(land_use)} zones)")
    
    # --- TAZ ---
    if 'TAZ' in land_use.columns:
        print("TAZ column already exists in land_use")
    else:
        taz_col = None
        for col in land_use.columns:
            if col.upper() in ['TAZ', 'TAZ_ID', 'TAZ_NO']:
                taz_col = col
                break
        
        if taz_col is None:
            print("Warning: Could not identify TAZ column in land_use, skipping TAZ rename")
        else:
            land_use = land_use.rename(columns={taz_col: 'TAZ'})
            print(f"Renamed land_use column '{taz_col}' to 'TAZ'")
    
    return land_use


def check_ids(
    households: pd.DataFrame, 
    persons: pd.DataFrame,
    fix_duplicates: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Check if household_id is unique. If not, create new unique IDs.
    
    Uses MAZ to match persons to the correct duplicated household.
    Original household_id is saved to non_unique_household_id.
    
    Parameters
    ----------
    households : pd.DataFrame
        Households table
    persons : pd.DataFrame
        Persons table
        
    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Updated (households, persons) DataFrames
    """
    # check for required columns
    assert "household_id" in households.columns, "households table missing household_id column"
    assert "household_id" in persons.columns, "persons table missing household_id column"
    assert "MAZ" in households.columns, "households table missing MAZ column"

    if "person_id" not in persons.columns:
        persons['person_id'] = persons.household_id * 100 + persons.groupby('household_id').cumcount() + 1

    assert persons.person_id.is_unique, "persons table person_id values are not unique"

    # Check for duplicates
    duplicate_mask = households.duplicated(subset=["household_id"], keep=False)
    num_duplicates = duplicate_mask.sum()
    
    if num_duplicates == 0:
        print("All household_id values are unique")
        return households, persons

    elif not fix_duplicates:
        print(
            f"Error: Found {num_duplicates} rows with duplicate household_id values:\n\t \
                {households[duplicate_mask].sort_values('household_id')}"
        )
        raise RuntimeError("Duplicate household_id values found. Set fix_duplicates=True to automatically create unique IDs.")
    else:
    
        print(
            f"Found {num_duplicates} rows with duplicate household_id values:\n\t \
                {households[duplicate_mask].sort_values('household_id')}"
        )

        # Save original household_id
        households["non_unique_household_id"] = households["household_id"]
        persons["non_unique_household_id"] = persons["household_id"]
        
        # Create new unique IDs for each duplicate row
        # Start new IDs from max existing ID + 1
        max_id = households["household_id"].max()
        
        # Assign a unique new ID to EACH row that has a duplicate household_id
        # (not just unique combinations, since same household_id + MAZ can appear multiple times)
        num_duplicates_to_fix = duplicate_mask.sum()
        households.loc[duplicate_mask, "household_id"] = range(
            max_id + 1, max_id + 1 + num_duplicates_to_fix
        )
        
        # Update persons table
        # Join persons with households to get MAZ, then map to new household_id
        persons_with_maz = persons.merge(
            households[["household_id", "non_unique_household_id", "MAZ"]].drop_duplicates(),
            left_on="non_unique_household_id",
            right_on="non_unique_household_id",
            how="left",
            suffixes=("_old", "")
        )
        
        # For persons that matched, use the new household_id
        if "household_id_old" in persons_with_maz.columns:
            persons_with_maz["household_id"] = persons_with_maz["household_id"].fillna(
                persons_with_maz["household_id_old"]
            )
            persons_with_maz = persons_with_maz.drop(columns=["household_id_old"])
        
        # Drop the MAZ column we added from the merge (keep original if exists)
        if "MAZ" in persons.columns:
            persons_with_maz = persons_with_maz.drop(columns=["MAZ"])
        
        persons = persons_with_maz
        
        # Verify the fix
        remaining_duplicates = households.duplicated(subset=["household_id"], keep=False).sum()
        if remaining_duplicates > 0:
            print(f"Warning: {remaining_duplicates} duplicate household_id values remain")
        else:
            print(f"Successfully created unique household_id values")
            print(f"Original IDs saved to 'non_unique_household_id' column")
        
        return households, persons


def add_transit_fare_factor(
    persons: pd.DataFrame,
    settings: PreprocessorSettings,
) -> pd.DataFrame:
    """Add person-level TRANSIT_FF using the Oregon transit fare rules."""
    if "TRANSIT_FF" in persons.columns:
        print("TRANSIT_FF column already exists in persons, skipping fare factor calculation")
        return persons

    fare_system = settings.transit_fare_system.get("name", "").upper() if settings.transit_fare_system else None
    valid_fare_systems = ["LTD", "CHERRIOTS", "TRIMET", "RVTD", "GRANTS_PASS", "FREE"]
    assert fare_system is None or fare_system in valid_fare_systems, f"Invalid transit_fare_system '{fare_system}'. Valid options are: {valid_fare_systems}"

    if fare_system is None:
        print("No transit_fare_system configured or inferred. Defaulting TRANSIT_FF to 1.0.")
        persons["TRANSIT_FF"] = 1.0
        return persons

    if fare_system == "FREE":
        persons["TRANSIT_FF"] = 0.0
        print("Added TRANSIT_FF to persons for free-fare transit service")
        return persons
    
    full_fare = settings.transit_fare_system["flat_fare_rate"]

    for column_name in ["age", "AGE", "AGEP"]:
        if column_name in persons.columns:
            age = pd.to_numeric(persons[column_name], errors="coerce")
            break
    else:
        raise RuntimeError("persons table must include an age column (one of: age, AGE, AGEP)")

    is_k12_student = persons.SCHG.fillna(-1).between(1, 14, inclusive="both")
    transit_ff = pd.Series(1.0, index=persons.index, dtype=float)

    if fare_system == "LTD":
        transit_ff.loc[age <= 18] = 0.85 / full_fare
        transit_ff.loc[(age <= 18) & is_k12_student] = 0.0
        transit_ff.loc[age <= 5] = 0.0
        transit_ff.loc[age >= 65] = 0.0
    elif fare_system == "CHERRIOTS":
        transit_ff.loc[age <= 18] = 0.0
        transit_ff.loc[age >= 60] = 0.80 / full_fare
    elif fare_system == "TRIMET":
        transit_ff.loc[age.between(7, 17, inclusive="both")] = 1.40 / full_fare
        transit_ff.loc[age <= 6] = 0.0
        transit_ff.loc[age >= 65] = 1.40 / full_fare
    elif fare_system == "RVTD":
        transit_ff.loc[age.between(10, 17, inclusive="both")] = 1.00 / full_fare
        transit_ff.loc[age <= 9] = 1.00 / full_fare
        transit_ff.loc[age >= 62] = 1.00 / full_fare
    elif fare_system == "GRANTS_PASS":
        transit_ff.loc[age.between(6, 16, inclusive="both")] = 0.50 / full_fare
        transit_ff.loc[age <= 5] = 0.0
        transit_ff.loc[age >= 62] = 0.50 / full_fare
    else:
        raise RuntimeError(f"Unsupported transit_fare_system '{fare_system}'")

    persons["TRANSIT_FF"] = transit_ff.round(3)
    print(f"Added TRANSIT_FF to persons using transit_fare_system='{fare_system}'")
    return persons


def add_tothhs(land_use: pd.DataFrame, households: pd.DataFrame) -> pd.DataFrame:
    """Add TOTHHS (total households per zone) to land_use if not present.
    Ensures TOTHHS values match the count of households in each MAZ, 
    and that the MAZ zones align between the two tables.
    
    Expects land_use to be indexed by MAZ.
    """
    tothhs = (
        households.groupby("MAZ")
        .size()
        .reindex(land_use.index)
        .fillna(0)
        .astype(int)
    )

    if "TOTHHS" not in land_use.columns:
        land_use["TOTHHS"] = tothhs
        print("Added TOTHHS to land_use")
    else:
        assert land_use["TOTHHS"].equals(tothhs), "Existing TOTHHS column does not match calculated values"

    return land_use


def add_totpop(land_use: pd.DataFrame, persons: pd.DataFrame, households: pd.DataFrame) -> pd.DataFrame:
    """Add TOTPOP (total population per zone) to land_use if not present.
    Ensures TOTPOP values match the count of persons in each MAZ,
    and that the MAZ zones align between the two tables.
    
    Expects land_use to be indexed by MAZ.
    """
    # Join persons to households to get MAZ
    if "MAZ" not in persons.columns:
        persons_with_zone = persons.merge(
            households[["household_id", "MAZ"]],
            on="household_id",
            how="left"
        )
    else:
        persons_with_zone = persons
    totpop = (
        persons_with_zone.groupby("MAZ")
        .size()
        .reindex(land_use.index)
        .fillna(0)
        .astype(int)
    )

    if "TOTPOP" not in land_use.columns:
        land_use["TOTPOP"] = totpop
        print("Added TOTPOP to land_use")
    else:
        assert land_use["TOTPOP"].equals(totpop), "Existing TOTPOP column does not match calculated values"
    return land_use


def add_acres(land_use: pd.DataFrame, maz_shp_file: str = None) -> pd.DataFrame:
    """Add ACRES to land_use if not present, calculating from shapefile.
    
    Parameters
    ----------
    land_use : pd.DataFrame
        Land use table with MAZ index
    maz_shp_file : str, optional
        Path to MAZ shapefile. Required if ACRES field is missing.
        
    Returns
    -------
    pd.DataFrame
        Updated land_use with ACRES field
    """
    # Drop exisiting ACRES col
    if "ACRES" in land_use.columns:
        land_use = land_use.drop(columns=["ACRES"], axis=1)
    
    if maz_shp_file is None:
        print("Warning: ACRES field not found and no maz_shp_file provided, skipping")
        return land_use
    
    print(f"Reading shapefile: {maz_shp_file}")
    gdf = gpd.read_file(maz_shp_file)
    
    # Ensure MAZ column is in shapefile
    maz_cols = [col for col in gdf.columns if 'MAZ' in col.upper()]
    
    if 'MAZ' not in gdf.columns:
        raise RuntimeError(
            f"'MAZ' column not in land use shapefile. Must add 'MAZ' column.\n"
            + (f"Available MAZ columns are: {maz_cols}. Change MAZ column name to 'MAZ'." if maz_cols else "")
        )
    
    if 'MAZ' in gdf.columns and len(maz_cols) > 1:
        print(f"Warning: Multiple MAZ columns identified in land use shapefile: {maz_cols}. Defaulting to 'MAZ'.")
    
    # Calculate area in acres
    # Convert to appropriate CRS if needed (shapefile should be in projected coordinates)
    if gdf.crs is None:
        print("Warning: Shapefile has no CRS defined, assuming units are in feet")
        sq_units_per_acre = 43560  # square feet per acre
    elif gdf.crs.is_geographic:
        print(f"Warning: Shapefile is in geographic CRS ({gdf.crs}), reprojecting to UTM for accurate area calculation")
        # Estimate UTM zone from centroid
        gdf = gdf.to_crs(gdf.estimate_utm_crs())
        sq_units_per_acre = 4046.86  # square meters per acre
    else:
        # Check the linear units of the projected CRS
        axis_info = gdf.crs.axis_info
        if axis_info and len(axis_info) > 0:
            unit_name = axis_info[0].unit_name.lower()
            if 'foot' in unit_name or 'feet' in unit_name or 'ft' in unit_name:
                sq_units_per_acre = 43560  # square feet per acre
                print(f"CRS units: feet")
            elif 'metre' in unit_name or 'meter' in unit_name or 'm' in unit_name:
                sq_units_per_acre = 4046.86  # square meters per acre
                print(f"CRS units: meters")
            else:
                raise RuntimeError("Warning: Could not determine CRS units from shapefile for ACRES calculation")
        else:
            raise RuntimeError("Warning: Could not determine CRS units from shapefile for ACRES calculation")
    
    # Calculate area in native units, then convert to acres
    gdf['ACRES'] = gdf.geometry.area / sq_units_per_acre
        
    # Add ACRES to land_use (merge on MAZ index)
    acres_map = gdf.set_index('MAZ')['ACRES']
    land_use['ACRES'] = acres_map.reindex(land_use.index).values
    
    # Check for missing values
    missing_count = land_use['ACRES'].isna().sum()
    if missing_count > 0:
        print(f"Warning: {missing_count} MAZ zones have no matching geometry in shapefile")
        # Fill missing with 0 or leave as NaN?
        land_use['ACRES'] = land_use['ACRES'].fillna(0)
    
    # Reasonableness checks
    min_acres = land_use['ACRES'].min()
    max_acres = land_use['ACRES'].max()
    mean_acres = land_use['ACRES'].mean()
    median_acres = land_use['ACRES'].median()
    
    print(f"Added ACRES to land_use (calculated from shapefile)")
    print(f"  Min: {min_acres:.2f}, Max: {max_acres:.2f}, Mean: {mean_acres:.2f}, Median: {median_acres:.2f}")
    
    # Sanity checks for typical urban MAZ sizes
    assert median_acres >= 0.1, f"Median ACRES ({median_acres:.4f}) seems too small. Check CRS units."
    assert median_acres <= 1000, f"Median ACRES ({median_acres:.2f}) seems too large. Check CRS units."
    # assert max_acres <= 50000, f"Max ACRES ({max_acres:.2f}) is very large. Some zones may be rural or external."
    assert min_acres >= 0, f"Negative ACRES detected ({min_acres:.4f}). Check for invalid geometries."
    
    return land_use


def merge_maz_stop_walk(land_use: pd.DataFrame, maz_stop_walk_file: str = None) -> pd.DataFrame:
    """Merge MAZ to stop walk distances to land_use.
    
    Parameters
    ----------
    land_use : pd.DataFrame
        Land use table with MAZ column
    maz_stop_walk_file : str, optional
        Path to MAZ stop walk distances CSV file.
        
    Returns
    -------
    pd.DataFrame
        Updated land_use with walk distance columns
    """
    if maz_stop_walk_file is None:
        print("No maz_stop_walk_file provided, skipping")
        return land_use
    
    print(f"Reading MAZ stop walk file: {maz_stop_walk_file}")
    maz_stop_walk = pd.read_csv(maz_stop_walk_file)
    
    # Check which columns will be added
    new_cols = [col for col in maz_stop_walk.columns if col != 'maz' and col not in land_use.columns]
    existing_cols = [col for col in maz_stop_walk.columns if col != 'maz' and col in land_use.columns]
    
    if existing_cols:
        print(f"  Columns already in land_use (skipping): {existing_cols}")
    
    if not new_cols:
        print("  All columns already exist in land_use, skipping merge")
        return land_use
    
    # Merge on MAZ index
    cols_to_merge = ['maz'] + new_cols
    stop_walk_indexed = maz_stop_walk[cols_to_merge].set_index('maz')
    land_use = land_use.join(stop_walk_indexed[new_cols], how='left')
    
    # Check for missing values
    for col in new_cols:
        missing_count = land_use[col].isna().sum()
        if missing_count > 0:
            print(f"  Warning: {missing_count} MAZ zones have no {col} value, filling with 0")
            land_use[col] = land_use[col].fillna(0)
    
    print(f"  Added columns to land_use: {new_cols}")
    
    return land_use

def get_intersection_count(
    settings: PreprocessorSettings, 
    land_use: pd.DataFrame
) -> pd.DataFrame:
    """ Count number of intersections in network 
    
    Parameters
    ----------
    land_use : pd.DataFrame
        Land use table with MAZ column
 
    Returns
    -------
    pd.DataFrame
        Updated land_use with intersection counts
    
    """ 
    print("Counting intersections for each MAZ...")  
    
    # Load settings 
    nodes_file = settings.nodes_file
    links_file = settings.links_file
    maz_shp_file = settings.maz_shp_file
    filter_col = settings.link_filter_col
    keep_link_types = settings.keep_link_types
    
    if nodes_file is None:
        print("Warning: missing node data, skipping intersection count")
        return land_use
    if links_file is None:
        print("Warning: missing link data, skipping intersection count")
        return land_use
    if maz_shp_file is None:
        print("Warning: missing maz_shp_file, skipping intersection count")
        return land_use
    
    # Load data
    print(f"Reading nodes file: {nodes_file}")
    nodes = gpd.read_file(nodes_file)
    print(f"Reading links file: {links_file}")
    links = gpd.read_file(links_file)
    print(f"Reading maz_shp_file: {maz_shp_file}")
    maz = gpd.read_file(settings.maz_shp_file)
    
    # Ensure MAZ is a column in land use shapefile
    maz_cols = [col for col in maz.columns if 'MAZ' in col.upper()]
    if 'MAZ' not in maz.columns:
        raise RuntimeError(
            f"'MAZ' column not in land use shapefile. Must add 'MAZ' column.\n"
            + (f"Available MAZ columns are: {maz_cols}. Change MAZ column name to 'MAZ'." if maz_cols else "")
        )
        
    if 'MAZ' in maz.columns and len(maz_cols) > 1:
        print(f"Warning: Multiple MAZ columns identified in land use shapefile: {maz_cols}. Defaulting to 'MAZ'.")
    
    links[filter_col] = pd.to_numeric(links[filter_col], errors='coerce')
    
    # Check crs
    if nodes.crs.is_geographic:
        print(f"Warning: Nodes shapefile is in geographic CRS ({nodes.crs}), reprojecting to UTM")
        nodes = nodes.to_crs(nodes.estimate_utm_crs())
           
    if maz.crs != nodes.crs:
        print(f"Converted maz shp to {nodes.crs}")
        maz = maz.to_crs(nodes.crs)
    
    # Filter links
    links = links[links[filter_col].isin(keep_link_types)]
    links['link_count'] = 1
    
    # Remove duplicate links
    links['link_AB'] = [tuple(sorted(x)) for x in zip(links['FROMNODENO'], links['TONODENO'])]
    links = links.drop_duplicates(subset='link_AB', keep='first')

    # Aggregate by NodeA and NodeB
    links_nodeA = links[['FROMNODENO', 'link_count']].groupby('FROMNODENO').sum().reset_index().rename(columns = {'FROMNODENO':'A'})
    links_nodeB = links[['TONODENO', 'link_count']].groupby("TONODENO").sum().reset_index().rename(columns = {'TONODENO':'B'})
    
    # Merge the two and keep all records from both dataframe (how='outer')
    nodes_linkcount = pd.merge(links_nodeA, links_nodeB, left_on='A', right_on = 'B', how='outer')
    nodes_linkcount = nodes_linkcount.fillna(0)
    nodes_linkcount['link_count'] = nodes_linkcount['link_count_x'] + nodes_linkcount['link_count_y']

    # Get node id from both dataframes
    nodes_linkcount['N'] = 0.0 # float
    nodes_linkcount.loc[nodes_linkcount.A > 0, 'N'] = nodes_linkcount['A']
    nodes_linkcount.loc[nodes_linkcount.B > 0, 'N'] = nodes_linkcount['B']
    nodes_linkcount = nodes_linkcount[['N', 'link_count']]
        
    # Keep nodes with 3+ links
    intersections_temp = nodes_linkcount.loc[nodes_linkcount.link_count >= 3]

    # Get node X and Y
    intersections = pd.merge(intersections_temp, nodes[['NO', 'XCOORD', 'YCOORD']], left_on='N', right_on='NO', how='left')
    intersections = intersections[['N', 'XCOORD', 'YCOORD']]
    intersections = intersections.rename(columns = {'XCOORD':'X', 'YCOORD':'Y'})
    
    # Find maz centroids
    maz['XCOORD'] = maz.geometry.centroid.x
    maz['YCOORD'] = maz.geometry.centroid.y
    maz_nodes = maz[['MAZ', 'XCOORD', 'YCOORD']]
    maz_nodes.columns = ['MAZ', 'X', 'Y']

    # Find nearest maz for each intersection
    print("Finding nearest MAZ for each intersection...")
    int_gdf = gpd.GeoDataFrame(
        intersections, geometry=gpd.points_from_xy(intersections['X'], intersections['Y']), crs=nodes.crs
    )
    maz_gdf = gpd.GeoDataFrame(
        maz_nodes, geometry=gpd.points_from_xy(maz_nodes['X'], maz_nodes['Y']), crs=nodes.crs
    )
    joined = gpd.sjoin_nearest(int_gdf, maz_gdf[['MAZ', 'geometry']], how='left')
    intersections['near_maz'] = joined['MAZ'].values
    intersections = intersections.groupby('near_maz', as_index = False).count()[['near_maz','N']].rename(columns = {'near_maz':'MAZ','N':'icnt'})
    
    # Merge counts with land use data (join on MAZ index)
    icnt_map = intersections.set_index('MAZ')['icnt']
    land_use['icnt'] = icnt_map.reindex(land_use.index).fillna(0)
    return land_use

def get_density(land_use: pd.DataFrame, settings: PreprocessorSettings,) -> pd.DataFrame:
    """Calculate land use densities and intersections
    
    Parameters
    ----------
    land_use : pd.DataFrame
        Land use table with MAZ column
        
    Returns
    -------
    pd.DataFrame
        Updated land_use with empden, retempden, duden,
        popden, popempdenpermi, totint
    
    """
    # Load settings
    if settings.maz_maz_walk_file is None:
        print("No maz_maz_walk file provided, skipping densities")
        return land_use
    
    print(f"Reading MAZ walk file: {settings.maz_maz_walk_file}")
    maz_maz_walk = pd.read_csv(settings.maz_maz_walk_file)
    
    # Drop existing density columns, accounting for case
    new_cols = ['empden', 'retempden', 'duden', 'popden', 'popempdenpermi', 'totint']
    lower_cols = {col.lower(): col for col in land_use.columns}
    for col in new_cols:
        if col in lower_cols:
            land_use = land_use.drop(lower_cols[col], axis=1)
    
    # Count intersections per MAZ
    if settings.count_intersections:
        land_use = get_intersection_count(settings, land_use)
        
    print("Calculating densities for each MAZ...")
    
    # Filter walk skim to only pairs within the density radius (once, upfront)
    nearby_pairs = maz_maz_walk.loc[
        maz_maz_walk['DISTWALK'] < settings.density_radius, ['OMAZ', 'j']
    ]
    
    # Prepare land_use lookup columns
    agg_cols = ['EMP_TOTAL', 'EMP_RET', 'TOTHHS', 'TOTPOP', 'ACRES']
    if settings.count_intersections:
        agg_cols.append('icnt')
    
    # Join land_use attributes onto each nearby pair by destination MAZ (index)
    nearby_with_data = nearby_pairs.merge(
        land_use[agg_cols],
        left_on='j',
        right_index=True,
        how='left'
    )
    
    # Sum attributes across all nearby MAZs for each origin MAZ
    sums = nearby_with_data.groupby('OMAZ')[agg_cols].sum()
    sums.index.name = 'MAZ'
    
    # Join sums back to land_use on the MAZ index
    sum_cols = {col: col + '_nearby' for col in agg_cols}
    sums = sums.rename(columns=sum_cols)
    land_use = land_use.join(sums, how='left')
    for sc in sum_cols.values():
        land_use[sc] = land_use[sc].fillna(0)
    
    # Calculate densities vectorized (avoid division by zero)
    has_acres = land_use['ACRES_nearby'] > 0
    land_use['empden'] = np.where(has_acres, land_use['EMP_TOTAL_nearby'] / land_use['ACRES_nearby'], 0.0)
    land_use['retempden'] = np.where(has_acres, land_use['EMP_RET_nearby'] / land_use['ACRES_nearby'], 0.0)
    land_use['duden'] = np.where(has_acres, land_use['TOTHHS_nearby'] / land_use['ACRES_nearby'], 0.0)
    land_use['popden'] = np.where(has_acres, land_use['TOTPOP_nearby'] / land_use['ACRES_nearby'], 0.0)
    land_use['popempdenpermi'] = np.where(
        has_acres,
        (land_use['EMP_TOTAL_nearby'] + land_use['TOTPOP_nearby']) / (land_use['ACRES_nearby'] / 640),
        0.0
    )
    
    if settings.count_intersections:
        land_use['totint'] = np.where(has_acres, land_use['icnt_nearby'], 0)
    else:
        print(f"Intersection counts provided. Using '{settings.icnt_col}' for 'totint'.")
        land_use['totint'] = land_use[settings.icnt_col]
    
    # Drop temporary nearby columns
    land_use = land_use.drop(columns=list(sum_cols.values()))    
    
    land_use[new_cols] = round(land_use[new_cols], 3)
    print(f"Added columns to land_use: {new_cols}")
    return land_use

def dataframes_equal(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """Check if two DataFrames are equal."""
    if df1.shape != df2.shape:
        return False
    if list(df1.columns) != list(df2.columns):
        return False
    return df1.equals(df2)


def write_output(
    settings: PreprocessorSettings,
    households: pd.DataFrame,
    persons: pd.DataFrame,
    land_use: pd.DataFrame,
    original_households: pd.DataFrame,
    original_persons: pd.DataFrame,
    original_land_use: pd.DataFrame,
) -> None:
    """
    Write output files to the output directory.
    
    If overwriting input files (output_dir is None), only write files that changed.
    """
    output_dir = settings.output_dir if settings.output_dir else settings.data_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    overwriting = settings.output_dir is None
    
    # Write households
    households_path = output_dir / 'households.csv'
    if overwriting and dataframes_equal(households, original_households):
        print(f"No changes to households, skipping write")
    else:
        households.to_csv(households_path, index=False)
        print(f"Saved households to {households_path}")
    
    # Write persons
    persons_path = output_dir / 'persons.csv'
    if overwriting and dataframes_equal(persons, original_persons):
        print(f"No changes to persons, skipping write")
    else:
        persons.to_csv(persons_path, index=False)
        print(f"Saved persons to {persons_path}")
    
    # Write land_use (include MAZ index as a column)
    land_use_path = output_dir / 'land_use.csv'
    if overwriting and dataframes_equal(land_use, original_land_use):
        print(f"No changes to land_use, skipping write")
    else:
        land_use.to_csv(land_use_path, index=True)
        print(f"Saved land_use to {land_use_path}")


def preprocess_fare_skim(settings: PreprocessorSettings) -> None:
    """Preprocess fare skim matrix into TOD format if needed.
    
    Parameters
    ----------
    settings : PreprocessorSettings
        Configuration settings for the preprocessor
    """
    # Placeholder for fare skim preprocessing logic
    # Implement as needed based on specific fare skim requirements
    print("Preprocessing fare skim matrix into TOD format")

    fare_skim_file = settings.fare_skim_input_file if hasattr(settings, 'fare_skim_input_file') else None
    if fare_skim_file is None:
        print("No fare_skim_input_file provided, skipping fare skim preprocessing")
        return
    
    input_fare_skim_file = omx.open_file(fare_skim_file)
    output_fare_skim_file_name = settings.output_dir / "fares.omx"

    with omx.open_file(output_fare_skim_file_name, 'w') as fare_skim_tod:
        # Example: Copy matrices and rename for TOD format
        matrices = input_fare_skim_file.list_matrices()
        assert len(matrices)  == 1, "Expeted only one matrix in fare skim file"

        for matrix_name in matrices:
            matrix = np.array(input_fare_skim_file[matrix_name])
            
            for time_period in settings.times_of_day:
                tod_matrix_name = f"fare__{time_period}"
                fare_skim_tod[tod_matrix_name] = matrix
                print(f"\tAdded matrix {tod_matrix_name} to fare skim TOD file")
        
        # write mapping to file
        # Set the shape on the output file first (required before creating mappings)
        mapping_name = input_fare_skim_file.list_mappings()[0]
        mapping_entries = np.array(list(input_fare_skim_file.mapping(mapping_name).keys()))
        fare_skim_tod.create_mapping(mapping_name, mapping_entries)
        print(f"\tCreated mapping {mapping_name} in fare skim TOD file")

    print(f"Saved fare skim TOD file to {output_fare_skim_file_name}")

    input_fare_skim_file.close()

def create_flat_fare_skim(settings: PreprocessorSettings, land_use: pd.DataFrame):
    """
    Create fares.omx for flat rate.
    
    Parameters
    ----------
    settings : PreprocessorSettings
        Configuration settings for the preprocessor
    
    Returns
    -------
    omx with matrices fare__[time_of_day]
    """
    print("Preprocessing flat-fare skim matrix.")
    if settings.transit_fare_system["flat_fare_rate"] is None:
        print("No flat-fare rate provided, skipping flat-fare skim creation.")
        return 
    
    flat_fare_rate = settings.transit_fare_system["flat_fare_rate"]
    assert flat_fare_rate >= 0, "Flat fare rate must be non-negative"
    print(f"Using flat fare rate of ${flat_fare_rate} for skim matrix")
    
    # Get TAZ IDs from land_use
    taz_ids = np.sort(land_use['TAZ'].unique())
    n_zones = len(taz_ids)
    
    # Create flat fare matrix
    fare_matrix = np.full((n_zones, n_zones), flat_fare_rate, dtype=np.float32)
    
    output_fare_skim_file_name = settings.output_dir / "fares.omx"
    with omx.open_file(output_fare_skim_file_name, 'w') as flat_fare_skim:
        for time_period in settings.times_of_day:
            tod_matrix_name = f"fare__{time_period}"
            flat_fare_skim[tod_matrix_name] = fare_matrix
            print(f"\tAdded matrix {tod_matrix_name} to fare skim TOD file")
            
        flat_fare_skim.create_mapping('taz', taz_ids)
    print(f"Saved flat-fare skim TOD file to {output_fare_skim_file_name}")
    
def add_exp_costs(land_use: pd.DataFrame, settings: PreprocessorSettings, ) -> pd.DataFrame:
    """
    Adds expected parking costs EXPPRK_HR, EXPPRK_DAY, EXPPRK_MNTH,
    if file is provided.
    
    Parameters
    ----------
    settings : PreprocessorSettings
        Configuration settings for the preprocessor
    land_use:
        Land use table with MAZ column
        
    Returns
    -------
    land_use:
        Updated dataframe with [EXPPRK_HR, EXPPRK_DAY, EXPPRK_MNTH]
    """
    
    if settings.exp_parking_costs_file is None:
        print("No expected parking costs file provided. Skipping adding exp costs.")
        return land_use
    
    exp_costs = pd.read_csv(settings.exp_parking_costs_file).rename(columns = {'mgra': 'MAZ'}).set_index('MAZ')
    exp_costs.index = exp_costs.index.astype(int)
    keep_cols = [col for col in exp_costs.columns if 'EXPPRK' in col] + ['PARKAREA']
    land_use = pd.merge(
        land_use, 
        exp_costs[keep_cols], 
        left_index=True,
        right_index=True, 
        how='left',
        validate='1:1')
    print(f"Added columns to land_use: {keep_cols}")
    return land_use
    
def preprocess(settings: PreprocessorSettings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Main preprocessing function.
    
    Parameters
    ----------
    settings : PreprocessorSettings
        Configuration settings for the preprocessor
    
    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
        Updated (households, persons, land_use) DataFrames
    """
    # Load data
    households, persons, land_use = load_data(settings)
    
    # Set MAZ as the land_use index
    land_use = set_land_use_maz_index(land_use)
    
    # Keep copies of originals for change detection
    original_households = households.copy()
    original_persons = persons.copy()
    original_land_use = land_use.copy()
    
    # Fix duplicate household IDs, check for correct names
    households, persons = check_ids(households, persons)

    # Add person-level transit fare factor from fare policy rules
    persons = add_transit_fare_factor(persons, settings)
    
    # Add TOTHHS and TOTPOP
    land_use = add_tothhs(land_use, households)
    land_use = add_totpop(land_use, persons, households)
    
    # Add ACRES if needed
    land_use = add_acres(land_use, settings.maz_shp_file)
    
    # Merge MAZ stop walk distances if provided
    land_use = merge_maz_stop_walk(land_use, settings.maz_stop_walk_file)
    
    # Calculate land use densities
    land_use = get_density(land_use, settings)
    
    # Add exp parking costs
    land_use = add_exp_costs(land_use, settings)
    
    # Write output files
    write_output(
        settings,
        households,
        persons,
        land_use,
        original_households,
        original_persons,
        original_land_use,
    )

    fare_skim_file = settings.fare_skim_input_file if hasattr(settings, 'fare_skim_input_file') else None

    if fare_skim_file is not None:
        # Preprocess fare skim matrix into TOD format if needed
        print(f"Preprocessing fare skim matrix from {fare_skim_file}")
        preprocess_fare_skim(settings)
    else:
        print("No fare skim input file provided, creating flat-fare skim.")
        # Create flat-fare skim with TOD format if needed
        create_flat_fare_skim(settings, land_use)
    
    return households, persons, land_use


if __name__ == "__main__":
    start_time = time.time()
    
    # Load settings from YAML if path provided, otherwise use defaults
    if len(sys.argv) > 1:
        yaml_path = Path(sys.argv[1])
        if not yaml_path.exists():
            print(f"Error: YAML file not found: {yaml_path}")
            sys.exit(1)
        settings = PreprocessorSettings.from_yaml(yaml_path)
        print(f"Loaded settings from {yaml_path}")
    else:
        settings = PreprocessorSettings()
        print("Using default settings")
    
    preprocess(settings)
    
    elapsed_time = time.time() - start_time
    print(f"\nPreprocessor completed in {elapsed_time:.2f} seconds")