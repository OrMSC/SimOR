# Setting up network links and connectors
# 11/12/2025 - Luke Gordon (RSG)
# Adapted from code from Chetan Joshi (PTV)

import tables
import numpy as np
import pandas as pd
import os
import VisumPy.helpers as h
import openmatrix as omx
import yaml


# YAML file constants management
# Get the folder where this script lives
script_dir = os.path.dirname(os.path.abspath(__file__))

# Go up directories to reach SimOR directory
folder_a = script_dir
while True:
    if os.path.basename(folder_a) == "SimOR":
        break
    parent = os.path.dirname(folder_a)
    if parent == folder_a:  # reached root directory
        raise FileNotFoundError("Folder 'SimOR' not found in parent hierarchy.")
    folder_a = parent

# Read the path from the pointer file
with open(os.path.join(folder_a, 'path_config.txt'), 'r') as f:
    yaml_relative_path = f.read().strip()

# Build the absolute path to the YAML file
yaml_path = os.path.join(folder_a, yaml_relative_path)

# Pull constants from the YAML file
with open(yaml_path, 'r') as file:
    config_data = yaml.safe_load(file)



def net_initialization():

    # Constants from Config.yaml
    walk_speed               =    Visum.Net.AttValue(r"Walk_Speed")                #config_data['Walk_Speed']              # 3.0 mph
    connector_vehicle_speed  =    Visum.Net.AttValue(r"Connector_Vehicle_Speed")   #config_data['Connector_Vehicle_Speed'] # 20 mph
    intrazonal_vehicle_speed =    Visum.Net.AttValue(r"Intrazonal_Vehicle_Speed")  #config_data['Intrazonal_Vehicle_Speed'] # 33.3333 mph

    # LINKS
    # Pull Attributes
    no          = h.GetMulti(Visum.Net.Links,r"NO"        , activeOnly = False)
    from_node   = h.GetMulti(Visum.Net.Links,r"FROMNODENO", activeOnly = False)
    to_node     = h.GetMulti(Visum.Net.Links,r"TONODENO"  , activeOnly = False)
    link_length = h.GetMulti(Visum.Net.Links,r"LENGTH"    , activeOnly = False)

    # Make Visum list with data
    att_list = [no,from_node,to_node,link_length]
    
	# Put Visum list into dataframe
    link_df = pd.DataFrame(np.column_stack(att_list), columns = ['no','from_node','to_node','link_length'])
    
    # Convert NO, FromNode, and ToNode to Strings
    link_df['no']          = link_df['no'].astype(int).astype(str)
    link_df['from_node']   = link_df['from_node'].astype(int).astype(str)
    link_df['to_node']     = link_df['to_node'].astype(int).astype(str)
    # Convert Length to float
    link_df['link_length'] = link_df['link_length'].astype(float)

    # Calculate LINKSERIAL and Walk Time
    link_df['linkserial'] = link_df['no'] + '-' + link_df['from_node'] + '-' + link_df['to_node']  
    link_df['wlk_time']   = link_df['link_length'] / (walk_speed/3600)

    # Set Calculated attributes on ALL links
    h.SetMulti(Visum.Net.Links ,r"LINKSERIAL" , link_df['linkserial'], activeOnly = False)
    h.SetMulti(Visum.Net.Links ,r"T_PUTSYS(W)", link_df['wlk_time']  , activeOnly = False)


    # CONNECTORS
    # Pull Attributes
    cc_length    = h.GetMulti(Visum.Net.Connectors,r"LENGTH"      , activeOnly = False)
    tsys         = h.GetMulti(Visum.Net.Connectors,r"TSYSSET"     , activeOnly = False)
    tsys_holding = h.GetMulti(Visum.Net.Connectors,r"TSYS_HOLDING", activeOnly = False) # Holding field that has the default "TSysSet" values pre KnR processes

    # Make Visum list with data
    att_list = [cc_length,tsys,tsys_holding]
    
	# Put Visum list into dataframe
    cc_df = pd.DataFrame(np.column_stack(att_list), columns = ['cc_length','tsys','tsys_holding'])

    # Convert Length to float
    cc_df['cc_length'] = cc_df['cc_length'].astype(float)

    # Calculate default connector times
    cc_df['veh_time'] = cc_df['cc_length'] / (connector_vehicle_speed/3600)
    cc_df['wlk_time'] = cc_df['cc_length'] / (walk_speed/3600)     

    # Set Calculated attributes on ALL connectors
    # Vehicles
    h.SetMulti(Visum.Net.Connectors ,r"ADDVAL1"      , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(C)"   , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(S)"   , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(SR2)" , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(SR3)" , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(MT)"  , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(HT)"  , cc_df['veh_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(I)"   , cc_df['veh_time'], activeOnly = False)
    # Walk
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(WLK)" , cc_df['wlk_time'], activeOnly = False)
    h.SetMulti(Visum.Net.Connectors ,r"T0_TSYS(W)"   , cc_df['wlk_time'], activeOnly = False)
    # TSys 
    if "i" in tsys: # Set to "holding" field if "i" (KnR) is in the connectors, the TSYSSET field is not correct
        h.SetMulti(Visum.Net.Connectors ,r"TSYSSET"      , cc_df['tsys_holding'], activeOnly = False)
    else:           # Set holding field to TSYSSET if "i" not in TSYSSET, the TSYSSET field is correct
        h.SetMulti(Visum.Net.Connectors ,r"TSYS_HOLDING" , cc_df['tsys']        , activeOnly = False)



    # ZONES
    # Intrazonal distance and time
    # Pull Attributes
    area      = h.GetMulti(Visum.Net.Zones,r"AREAMI2", activeOnly = False)
    intrdist  = h.GetMulti(Visum.Net.Zones,r"INTRDIST", activeOnly = False) 
    intrtime  = h.GetMulti(Visum.Net.Zones,r"INTRTIME", activeOnly = False)

    # Make Visum list with data
    att_list = [area,intrdist,intrtime]
    
	# Put Visum list into dataframe
    zone_df = pd.DataFrame(np.column_stack(att_list), columns = ['area','intrdist','intrtime'])

    # Convert Area to Acres
    zone_df['acres'] = zone_df['area'] * 640

    # Calculate intrdist and intrtime
    zone_df['intrdist'] = np.minimum(np.sqrt(zone_df['acres']) * 0.024 , 0.75)
    zone_df['intrtime'] = np.minimum((zone_df['intrdist'] / intrazonal_vehicle_speed) * 3600 , 72)

    # Set Calculated attributes on ALL Zones
    h.SetMulti(Visum.Net.Zones ,r"INTRDIST"      , zone_df['intrdist'], activeOnly = False)
    h.SetMulti(Visum.Net.Zones ,r"INTRDIST_WLK"  , zone_df['intrdist'], activeOnly = False)
    h.SetMulti(Visum.Net.Zones ,r"INTRTIME"      , zone_df['intrtime'], activeOnly = False)


net_initialization()

