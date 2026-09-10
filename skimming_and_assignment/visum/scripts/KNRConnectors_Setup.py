
#script to insert KNR connectors
# Chetan Joshi, PTV Portland OR 6/25/2025

import numpy as np
import scipy.spatial
import json 
import csv
import os
import VisumPy.helpers as h
import pandas as pd
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


PRIO = 20480
_TABLE = "KnRConstraints"
SCALEFACTOR = config_data['SCALEFACTOR']  # 5280

# FN = os.path.join(Visum.GetPath(2), "taz_connectors.json")
FN = os.path.join(Visum.GetPath(2), "connectors_knr.net")

def vision_header():
    vision_head = [["$VISION"],
                   ["$VERSION:VERSNR", "FILETYPE", "LANGUAGE", "UNIT"],
                   [15,"Net","ENG","MI"]]
    return vision_head


def create_knr_connectors():

    # Check for type 10 connectors (knr connectors), if they exist, don't add any more connectors
    checktype = np.array(h.GetMulti(Visum.Net.Connectors,r"TYPENO", activeOnly = True))
    if 10 in checktype:
        Visum.Log(PRIO, 'KNR connectors already built!')
        # Save original TSysSet in TSYS_HOLDING for later use
        #tsysorig = h.GetMulti(Visum.Net.Connectors,r"TSYSSET", activeOnly = True)
        #h.SetMulti(Visum.Net.Connectors, r"TSYS_HOLDING", tsysorig)

        return
    else:
        Visum.Log(PRIO, 'Building KNR Connectors')
        # Save original TSysSet in TSYS_HOLDING for later use
        #tsysorig = h.GetMulti(Visum.Net.Connectors,r"TSYSSET", activeOnly = True)
        #h.SetMulti(Visum.Net.Connectors, r"TSYS_HOLDING", tsysorig)



    Visum.Log(PRIO, 'generate search list...')
    tsys_constr = dict([tsys, [maxdist, maxstops]] for tsys, maxdist, maxstops in Visum.Net.TableDefinitions.ItemByKey(_TABLE).TableEntries.GetMultipleAttributes(["TSYS", "MAXDIST", "MAXSTOPS"]))
    
    cutoff = 5*SCALEFACTOR
    tazs   = Visum.Net.Zones.GetMultiAttValues("NO", False)
    stp_no = np.array(Visum.Net.StopAreas.GetMultiAttValues("NO", False), dtype='int')[:, 1]
    stop_tsys = dict([[sno, [nodeno, tsys]] for sno, nodeno, tsys in Visum.Net.StopAreas.GetMultipleAttributes(["NO", "NODENO", "DISTINCT:STOPPOINTS\\TSYSSET"])])
    taz_xy = np.array(Visum.Net.Zones.GetMultipleAttributes(["XCOORD", "YCOORD"], False))
    stp_xy = np.array(Visum.Net.StopAreas.GetMultipleAttributes(["XCOORD", "YCOORD"], False))

    Visum.Log(PRIO, 'calculate nearest stop in catchment for each taz...')

    distance = scipy.spatial.distance.cdist(taz_xy, stp_xy, 'euclidean')
    result   = dict()
    connector_table = [["$CONNECTOR:ZONENO","NODENO","DIRECTION","TYPENO","TSYSSET"]]
    for ix, taz in tazs:
        connector_nodes     = set()
        catchment_stops     = stp_no.compress(distance[ix-1, :] <= cutoff)
        catchment_distance  = distance[ix-1, :].compress(distance[ix-1, :]  <= cutoff)

        for tsys in tsys_constr:
            max_dist, max_stops = tsys_constr[tsys]
            max_dist = max_dist*SCALEFACTOR
            stops_added = 0
            for dist, stopno in sorted(zip(catchment_distance, catchment_stops)):
                snode, stsys = stop_tsys[stopno]
                stsys = stsys.split(",")
                if dist < max_dist and tsys in stsys:
                    connector_nodes.add(snode)
                    stops_added+=1
                if stops_added >= max_stops:
                    break 
        
        result[taz] = list(connector_nodes)

        # GENERATE NET FILE BATCH TABLE FOR CONNECTORS. 
        # need to preserve original connectors esp: walk to destination(?)
        for node in connector_nodes:
            # --- ["$CONNECTOR:ZONENO","NODENO","DIRECTION","TYPENO"]
            if Visum.Net.Connectors.ExistsByKey(node, taz):
                # Visum.Log(PRIO, "{} -> {} | already exists!".format(taz, node))
                connector_table.append([taz, node, 'O', 7, 'i'])  # origin/access connector
                dtsys = Visum.Net.Connectors.DestItemByKey(node, taz).AttValue("TSYSSET")
                connector_table.append([taz, node, 'D', 7, dtsys])   # destination/egress connector
            else:
                connector_table.append([taz, node, 'O', 10, ''])  # origin/access connector
                connector_table.append([taz, node, 'D', 10, ''])  # destination/egress connector

    Visum.Log(PRIO, 'write results to file...')
    # with open(FN, 'w') as out_file:
    #     json.dump(result, out_file, indent=2)

    with open(FN, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter =';')
        writer.writerows(vision_header())
        writer.writerows(connector_table) 

    Visum.Log(PRIO, 'read knr connectors...')

    loadnetctrl = Visum.IO.CreateAddNetReadController()  # read additionally controller
    loadnetctrl.SetWhatToDo("CONNECTOR", 5)              # conflict handling - overwrite attributes
    Visum.IO.LoadNet(FN, ReadAdditive=True, RouteSearch=None, AddNetRead=loadnetctrl, NormalizePolygons=False, 
                     MergeSameCoordPolygonPoints=False, DecimalsForMergeSameCoordPolygonPoints=-1)
    
    # Set Length for new connectors based on preexisting connector lengths (which come from Emme originally)
    length   = h.GetMulti(Visum.Net.Connectors,r"LENGTH"    , activeOnly = True)
    zoneno   = h.GetMulti(Visum.Net.Connectors,r"ZONENO"    , activeOnly = True)
    typeno   = h.GetMulti(Visum.Net.Connectors,r"TYPENO"    , activeOnly = True)
    att_list = [length,zoneno,typeno]
    df = pd.DataFrame(np.column_stack(att_list), columns = ['length','zoneno','typeno'])
    df_filtered = df[df['typeno'] < 10]  # All preexisting connectors will be TypeNO = 0 or 7
    df_unique = df_filtered.groupby('zoneno').agg(length_max=('length', 'max')).reset_index()
    df = pd.merge(df, df_unique, on='zoneno', how='left')
    #df['length_max'] = df['length_max'].fillna(df['length'])
    h.SetMulti(Visum.Net.Connectors,r"LENGTH"    ,df['length_max'])



    Visum.Log(PRIO, 'done!')


def set_connector_properties(knrdirection):

    # Save TSysSet in TSys_Holding if the original values are present in TSysSet
    checktype = np.array(h.GetMulti(Visum.Net.Connectors,r"TSYSSET", activeOnly = True))
    if 'i' in checktype:
        Visum.Log(PRIO, 'TSYS_HOLDING Overwriting Skipped')
    else:
        Visum.Log(PRIO, 'TSYS_HOLDING Overwritten')
        tsys = h.GetMulti(Visum.Net.Connectors,r"TSYSSET", activeOnly = True)
        h.SetMulti(Visum.Net.Connectors,r"TSYS_HOLDING"  ,tsys)

    # Pull attributes
    connector_type_dir = Visum.Net.Connectors.GetMultipleAttributes(["TypeNo", "Direction", "Length", "TSYS_HOLDING"])
    connector_tsys = []
    #connector_time = []     
    # we assume here that KNR is not open on any connector to start
    for typeno, direction, distance, tsys_hold in connector_type_dir:
        if knrdirection == "KTW":    
            if direction == 1: # Origin, leaving a zone
                if typeno in [7, 10]:
                    connector_tsys.append("i")
                else:
                    connector_tsys.append("")
            
            elif direction == 2: # Destination, entering a zone
                if typeno == 10:
                    # a knr drive only connector- so no walk on this.
                    connector_tsys.append("")
                else:
                    # could be a walk destination connector, 
                    # we assume here that KNR is not open on any connector to start so keep Tsys the way it was (else: could also set to 'w')
                    connector_tsys.append(tsys_hold)
        elif knrdirection == "WTK":    
            if direction == 2: # Destination, entering a zone
                if typeno in [7, 10]:
                    connector_tsys.append("i")
                else:
                    connector_tsys.append("")
            elif direction == 1: # Origin, leaving a zone
                if typeno == 10:
                    # a knr drive only connector- so no walk on this.
                    connector_tsys.append("")
                else:
                    # could be a walk destination connector, 
                    # we assume here that KNR is not open on any connector to start so keep Tsys the way it was (else: could also set to 'w')
                    connector_tsys.append(tsys_hold)
        elif knrdirection == "WTW":
            connector_tsys.append(tsys_hold)
    
    h.SetMulti(Visum.Net.Connectors, "TSysSet", connector_tsys)



code = Visum.Procedures.OperationExecutor.GetCurrentOperation().AttValue("CODE")  
create_knr_connectors()
set_connector_properties(code)
