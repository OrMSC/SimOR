# This script generates MAZ and TAZ connectors with two links per connector, one for each direction
import pandas as pd
import geopandas as gpd
import numpy as np
import os
from shapely import LineString, wkt

# Settings
mpo = "SKATS" #LCOG, SKATS
visum_outputs_dir = f"C:/Users/edna.aguilar/Documents/git_locals/SimOR/skimming_and_assignment/maz_maz_stop_skims/Visum_Outputs_{mpo}"
maz_output_file = os.path.join(f"LinkNodeTurns_{mpo}", "maz_connectors.shp")
taz_output_file = os.path.join(f"LinkNodeTurns_{mpo}", "taz_connectors.shp")
maz_output_csv = os.path.join(f"LinkNodeTurns_{mpo}", "maz_connectors.csv")
taz_output_csv = os.path.join(f"LinkNodeTurns_{mpo}", "taz_connectors.csv")

# Load links
link_file = f"LinkNodeTurns_{mpo}/links.csv"
node_file = f"LinkNodeTurns_{mpo}/nodes.csv"
maz_file = f"{visum_outputs_dir}/MAZ_poi_surface.shp"

# External station are points for LCOG, load separately
if mpo == "LCOG":
    ext_points = gpd.read_file(f"{visum_outputs_dir}/MAZ_poi_centroid.shp")
    ext_points = ext_points[ext_points["NO"] >= 5000]

mazs = gpd.read_file(maz_file)
links = gpd.read_file(link_file)
nodes = gpd.read_file(node_file)

# Convert to same crs
assert (mazs.crs.is_projected), "MAZ crs is not projected"

# Create links and nodes
nodes['geometry'] = nodes['WKTLOCWGS84'].apply(wkt.loads)
nodes["NO"] = pd.to_numeric(nodes["NO"], errors="coerce")
nodes = gpd.GeoDataFrame(nodes, geometry="geometry", crs="4326")
nodes.to_file(os.path.join(f"LinkNodeTurns_{mpo}", "bike_nodes.shp"))
nodes = nodes.to_crs(mazs.crs)

links['geometry'] = links['WKTPOLYWGS84'].apply(wkt.loads)
links = gpd.GeoDataFrame(links, geometry="geometry", crs="4326")
links.to_file(os.path.join(f"LinkNodeTurns_{mpo}", "bike_links.shp"))
links = links.to_crs(mazs.crs)

# Get TAZ centroids
tazs = mazs[['TAZ', 'geometry']].dissolve('TAZ').reset_index()
taz_centroids = tazs.copy()

if mpo == "LCOG":
    taz_centroids = pd.concat(
        [taz_centroids, ext_points[["TAZ", "geometry"]]], 
        axis=0, ignore_index=True
        ).reset_index()
    
taz_centroids["centroid_geom"] = taz_centroids['geometry'].centroid
taz_centroids = taz_centroids[["TAZ", "centroid_geom"]].rename(columns={'centroid_geom':'geometry'})

# Get MAZ centroids
maz_centroids = mazs[['MAZ', "geometry"]].copy()

if mpo == "LCOG":
    maz_centroids = pd.concat(
        [maz_centroids, ext_points[["MAZ", "geometry"]]], 
        axis=0, ignore_index=True
        ).reset_index()
    
maz_centroids['centroid_geom'] = maz_centroids['geometry'].centroid
maz_centroids = maz_centroids[["MAZ", "centroid_geom"]].rename(columns={"centroid_geom":"geometry"}) 

# ================
# Create connectors
def add_connectors(centroids, nodes, zone_id):
    centroids['ZONENO'] = centroids[zone_id]
    
    # Find nearest node from centroid
    centroids_to_nearest_node = gpd.sjoin_nearest(
        centroids, nodes[["NO", "geometry"]], how="left", distance_col="distance"
    )
    
    # Create connector polyline from centroid to nearest node
    centroids_to_nearest_node = centroids_to_nearest_node.merge(
            nodes[["NO", "geometry"]],
            on="NO",
            how="left",
            suffixes=("_left", "_right")
        )
    
    centroids_to_nearest_node["geometry"] = centroids_to_nearest_node.apply(
        lambda row: LineString([row["geometry_right"], row["geometry_left"]]), axis=1
    )
    
    # Call nearest node "TONODENO"
    maz_connectors = centroids_to_nearest_node.rename(columns = {'NO': 'NODENO'})
    
    # Convert to gdf
    maz_connectors =gpd.GeoDataFrame(
        maz_connectors[['ZONENO', 'NODENO', 'geometry']], 
        geometry="geometry", 
        crs=centroids.crs)
    
    # Add length
    maz_connectors["LENGTH"] = maz_connectors["geometry"].length
    
    # Duplicate connectors to create second direction
    maz_connectors['DIRECTION'] = 1
    maz_connectors2 = maz_connectors.copy()
    
    # For duplicates, change polyline coordinate order
    maz_connectors2['DIRECTION'] = 2
    maz_connectors2['geometry'] = maz_connectors2['geometry'].apply(
    lambda geom: LineString(list(geom.coords)[::-1])
    )
    
    maz_connectors_final = pd.concat(
        [maz_connectors, maz_connectors2],
        axis=0,
        ignore_index=True
        ).sort_values(by=["ZONENO", "NODENO"])
    
    # Add wkt geometry
    maz_connectors_final = maz_connectors_final.to_crs(4326)
    maz_connectors_final["WKTLOCWGS84"] = maz_connectors_final.geometry.to_wkt()

    return maz_connectors_final.reset_index(drop=True)

maz_connectors = add_connectors(maz_centroids, nodes, 'MAZ')
taz_connectors = add_connectors(taz_centroids, nodes, 'TAZ')

# Export
maz_connectors.to_file(maz_output_file)
taz_connectors.to_file(taz_output_file)

maz_connectors.drop(columns=["geometry"]).to_csv(maz_output_csv, index = False)
taz_connectors.drop(columns=["geometry"]).to_csv(taz_output_csv, index = False)