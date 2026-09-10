# Post-processing PuT skims from Visum based on "Code" field in Procedure Sequence
# 6/16/2025 - Luke Gordon (RSG)
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



# Create function to build skim matrices that weren't built during the skimming procedure itself if they don't yet exist
def creatematrices(code,mtx_dseg):
    try:
        mx = h.GetMatrixRaw(Visum, {"CODE": code , "DSegCode": mtx_dseg})
    except Exception as e:
        mx = Visum.Net.AddMatrix(No=-1,ObjectTypeRef=2,MatrixType=4)
        mx.SetAttValue("CODE",code)
        mx.SetAttValue("DSegCode",mtx_dseg)


def putskim_postprocessing(mtx_dseg,knr_flag):
    
    # Build matrices if they don't yet exist
    creatematrices("NBR" ,mtx_dseg)
    creatematrices("IVTT",mtx_dseg)
    creatematrices("STC" ,mtx_dseg)
    creatematrices("VTC" ,mtx_dseg)

    # Pull matrices out of Visum as numpy arrays
    twpt   = h.GetMatrixRaw(Visum, {"CODE": "TWPT"    , "DSegCode": mtx_dseg})  # Transfer Walk Path time    (formerly walk time)
    owpt   = h.GetMatrixRaw(Visum, {"CODE": "OWPT"    , "DSegCode": mtx_dseg})  # Origin Walk Path time      (formerly access time)
    dwpt   = h.GetMatrixRaw(Visum, {"CODE": "DWPT"    , "DSegCode": mtx_dseg})  # Destination Walk Path time (formerly egress time)
    ntr    = h.GetMatrixRaw(Visum, {"CODE": "NTR"     , "DSegCode": mtx_dseg})  # Number of transfers
    nbr    = h.GetMatrixRaw(Visum, {"CODE": "NBR"     , "DSegCode": mtx_dseg})  # Number of boardings
    wowt   = h.GetMatrixRaw(Visum, {"CODE": "WOWT"    , "DSegCode": mtx_dseg})  # Weighted origin wait time
    wtwt   = h.GetMatrixRaw(Visum, {"CODE": "WTWT"    , "DSegCode": mtx_dseg})  # Weighted transfer wait time
    ivtt   = h.GetMatrixRaw(Visum, {"CODE": "IVTT"    , "DSegCode": mtx_dseg})  # In-vehicle travel time
    ivtt_a = h.GetMatrixRaw(Visum, {"CODE": "IVTT(a)" , "DSegCode": mtx_dseg})  # In-vehicle travel time (BRT)
    ivtt_b = h.GetMatrixRaw(Visum, {"CODE": "IVTT(b)" , "DSegCode": mtx_dseg})  # In-vehicle travel time (Bus)
    ivtt_e = h.GetMatrixRaw(Visum, {"CODE": "IVTT(e)" , "DSegCode": mtx_dseg})  # In-vehicle travel time (Streetcar)
    ivtt_l = h.GetMatrixRaw(Visum, {"CODE": "IVTT(l)" , "DSegCode": mtx_dseg})  # In-vehicle travel time (LRT)
    ivtt_r = h.GetMatrixRaw(Visum, {"CODE": "IVTT(r)" , "DSegCode": mtx_dseg})  # In-vehicle travel time (WES)
    pla    = h.GetMatrixRaw(Visum, {"CODE": "PLA"     , "DSegCode": mtx_dseg})  # Stop type constant (raw sum)
    stc    = h.GetMatrixRaw(Visum, {"CODE": "STC"     , "DSegCode": mtx_dseg})  # Stop type constant (final average)
    vtc    = h.GetMatrixRaw(Visum, {"CODE": "VTC"     , "DSegCode": mtx_dseg})  # Vehicle type constant
    acd    = h.GetMatrixRaw(Visum, {"CODE": "ACD"     , "DSegCode": mtx_dseg})  # Access Distance (used for KNR-Transit-Walk drive  to  transit distance)
    egd    = h.GetMatrixRaw(Visum, {"CODE": "EGD"     , "DSegCode": mtx_dseg})  # Egress Distance (used for Walk-Transit-KNR drive from transit distance)

    # Process matrices
    # Set maximum walk time allowed
    wlkspeed            = Visum.Net.AttValue(r"Walk_Speed")
    origin_maxwlktime   = 1.00 * (60 / wlkspeed) # Minutes to walk 1 mile
    dest_maxwlktime     = 1.00 * (60 / wlkspeed) # Minutes to walk 1 mile
    transfer_maxwlktime = 0.25 * (60 / wlkspeed) # Minutes to walk 0.25 miles

    # Flag for which walk masking to run (New for Visum or Old for Emme)
    updated_walkskim_masking = 1
    
    if updated_walkskim_masking == 1:
        # CHANGE TO BE MAX WALK DISTANCE BY Transfer Walk Path time (0.25 mi), Origin Walk Path time (1 mi), Destination Walk Path time (1 mi)
        # Mask Transfer Walk Path time
        if knr_flag == 'wtw':
            twpt = np.where((owpt > origin_maxwlktime) | (dwpt > dest_maxwlktime) | (twpt > transfer_maxwlktime) , 9999.00, twpt)
            np.fill_diagonal(twpt, 9999.00)
        elif knr_flag == 'ktw':
            twpt = np.where((dwpt > dest_maxwlktime)   | (twpt > transfer_maxwlktime) , 9999.00, twpt)
            np.fill_diagonal(twpt, 9999.00)
        elif knr_flag == 'wtk':
            twpt = np.where((owpt > origin_maxwlktime) | (twpt > transfer_maxwlktime) , 9999.00, twpt)
            np.fill_diagonal(twpt, 9999.00)

    
    if updated_walkskim_masking == 0:
        # !!!!!! MASKING FOR COMPARISON WITH EMME (TEMPORARY) !!!!!!!
        # Mask Transfer Walk Path time  GREATER THAN 20 MINUTES TOTAL WALK, GREATER THAN 30 MINUTES ORIGIN OR TRANSFER WAIT TIME
        if knr_flag == 'wtw':
            twpt = np.where((owpt + dwpt + twpt > 20), 9999.00, twpt)
            np.fill_diagonal(twpt, 9999.00)
            wowt = np.where((wowt > 30), 30.00, wowt)
            wtwt = np.where((wtwt > 30), 30.00, wtwt)
        elif knr_flag == 'ktw':
            twpt = np.where((dwpt + twpt > 20), 9999.00, twpt)
            np.fill_diagonal(twpt, 9999.00)
            wowt = np.where((wowt > 30), 30.00, wowt)
            wtwt = np.where((wtwt > 30), 30.00, wtwt)
        elif knr_flag == 'wtk':
            twpt = np.where((owpt + twpt > 20), 9999.00, twpt)
            np.fill_diagonal(twpt, 9999.00)
            wowt = np.where((wowt > 30), 30.00, wowt)
            wtwt = np.where((wtwt > 30), 30.00, wtwt)
        # !!!!!! TEMPORARY !!!!!!


    # MASKING: Set all matrices to have matrix cells = 9999.00 if twpt = 9999.00
    owpt   = np.where(twpt == 9999.00, 9999.00, owpt)
    dwpt   = np.where(twpt == 9999.00, 9999.00, dwpt)
    ntr    = np.where(twpt == 9999.00, 9999.00, ntr)
    nbr    = np.where(twpt == 9999.00, 9999.00, nbr)
    wowt   = np.where(twpt == 9999.00, 9999.00, wowt)
    wtwt   = np.where(twpt == 9999.00, 9999.00, wtwt)
    ivtt   = np.where(twpt == 9999.00, 9999.00, ivtt)
    ivtt_a = np.where(twpt == 9999.00, 9999.00, ivtt_a)
    ivtt_b = np.where(twpt == 9999.00, 9999.00, ivtt_b)
    ivtt_e = np.where(twpt == 9999.00, 9999.00, ivtt_e)
    ivtt_l = np.where(twpt == 9999.00, 9999.00, ivtt_l)
    ivtt_r = np.where(twpt == 9999.00, 9999.00, ivtt_r)
    pla    = np.where(twpt == 9999.00, 9999.00, pla)
    stc    = np.where(twpt == 9999.00, 9999.00, stc)
    vtc    = np.where(twpt == 9999.00, 9999.00, vtc)
    acd    = np.where(twpt == 9999.00, 9999.00, acd)
    egd    = np.where(twpt == 9999.00, 9999.00, egd)

    # Perceived In-vehicle time by Mode
    if mtx_dseg == 'amPuT' or mtx_dseg == 'pmPuT':                      # Peak
        ivtt_a = np.where(ivtt_a == 9999.00, 9999.00, ivtt_a * config_data['PkIVPFa'])
        ivtt_l = np.where(ivtt_l == 9999.00, 9999.00, ivtt_l * config_data['PkIVPFl'])
        ivtt_r = np.where(ivtt_r == 9999.00, 9999.00, ivtt_r * config_data['PkIVPFr'])
    else:                                                               # Off-Peak
        ivtt_a = np.where(ivtt_a == 9999.00, 9999.00, ivtt_a * config_data['OpIVPFa'])
        ivtt_l = np.where(ivtt_l == 9999.00, 9999.00, ivtt_l * config_data['OpIVPFl'])
        ivtt_r = np.where(ivtt_r == 9999.00, 9999.00, ivtt_r * config_data['OpIVPFr'])

    # Number of boardings
    nbr = np.where(ntr == 9999.00, 9999.00, ntr + 1)

    # Stop type constant
    stc = np.where((pla == 9999.00) | (nbr == 9999.00) , 9999.00, pla / nbr)
    stc = np.where(stc == 9999.00, 0.00, stc)

    # In-Vehicle time
    ivtt = np.minimum(ivtt_a + ivtt_b + ivtt_e + ivtt_l + ivtt_r, 9999.00)
    np.fill_diagonal(ivtt, 9999.00)

    # Vehicle type constant
    if mtx_dseg == 'amPuT' or mtx_dseg == 'pmPuT':                                                                                          # Peak
        vtc = np.where((ivtt == 9999.00) | (ivtt == 0.00), 9999.00, 
                       ((config_data['PkVTCa'] * ivtt_a) / ivtt) + ((config_data['PkVTCe'] * ivtt_e) / ivtt) + ((config_data['PkVTCl'] * ivtt_l) / ivtt) + ((config_data['PkVTCr'] * ivtt_r) / ivtt))
    else:                                                                                                                                   # Off-Peak
        vtc = np.where((ivtt == 9999.00) | (ivtt == 0.00), 9999.00, 
                       ((config_data['OpVTCa'] * ivtt_a) / ivtt) + ((config_data['OpVTCe'] * ivtt_e) / ivtt) + ((config_data['OpVTCl'] * ivtt_l) / ivtt) + ((config_data['OpVTCr'] * ivtt_r) / ivtt))

    # Set matrices in Visum
    #h.SetMatrixRaw(Visum, {"CODE": "WKT"     , "DSegCode": mtx_dseg}, wkt   )  # Walk time
    #h.SetMatrixRaw(Visum, {"CODE": "ACT"     , "DSegCode": mtx_dseg}, act   )  # Access time
    #h.SetMatrixRaw(Visum, {"CODE": "EGT"     , "DSegCode": mtx_dseg}, egt   )  # Egress time

    h.SetMatrixRaw(Visum, {"CODE": "TWPT"    , "DSegCode": mtx_dseg}, twpt  )  # Transfer Walk Path time    (formerly walk time)
    h.SetMatrixRaw(Visum, {"CODE": "OWPT"    , "DSegCode": mtx_dseg}, owpt  )  # Origin Walk Path time      (formerly access time)
    h.SetMatrixRaw(Visum, {"CODE": "DWPT"    , "DSegCode": mtx_dseg}, dwpt  )  # Destination Walk Path time (formerly egress time)
    h.SetMatrixRaw(Visum, {"CODE": "NTR"     , "DSegCode": mtx_dseg}, ntr   )  # Number of transfers
    h.SetMatrixRaw(Visum, {"CODE": "NBR"     , "DSegCode": mtx_dseg}, nbr   )  # Number of boardings
    h.SetMatrixRaw(Visum, {"CODE": "WOWT"    , "DSegCode": mtx_dseg}, wowt  )  # Weighted origin wait time
    h.SetMatrixRaw(Visum, {"CODE": "WTWT"    , "DSegCode": mtx_dseg}, wtwt  )  # Weighted transfer wait time
    h.SetMatrixRaw(Visum, {"CODE": "IVTT"    , "DSegCode": mtx_dseg}, ivtt  )  # In-vehicle travel time
    h.SetMatrixRaw(Visum, {"CODE": "IVTT(a)" , "DSegCode": mtx_dseg}, ivtt_a)  # In-vehicle travel time (BRT)
    h.SetMatrixRaw(Visum, {"CODE": "IVTT(b)" , "DSegCode": mtx_dseg}, ivtt_b)  # In-vehicle travel time (Bus)
    h.SetMatrixRaw(Visum, {"CODE": "IVTT(e)" , "DSegCode": mtx_dseg}, ivtt_e)  # In-vehicle travel time (Streetcar)
    h.SetMatrixRaw(Visum, {"CODE": "IVTT(l)" , "DSegCode": mtx_dseg}, ivtt_l)  # In-vehicle travel time (LRT)
    h.SetMatrixRaw(Visum, {"CODE": "IVTT(r)" , "DSegCode": mtx_dseg}, ivtt_r)  # In-vehicle travel time (WES)
    h.SetMatrixRaw(Visum, {"CODE": "PLA"     , "DSegCode": mtx_dseg}, pla   )  # Stop type constant (raw sum)
    h.SetMatrixRaw(Visum, {"CODE": "STC"     , "DSegCode": mtx_dseg}, stc   )  # Stop type constant (final average)
    h.SetMatrixRaw(Visum, {"CODE": "VTC"     , "DSegCode": mtx_dseg}, vtc   )  # Vehicle type constant
    h.SetMatrixRaw(Visum, {"CODE": "ACD"     , "DSegCode": mtx_dseg}, acd   )  # Access (used for KNR-Transit-Walk drive to transit time)
    h.SetMatrixRaw(Visum, {"CODE": "EGD"     , "DSegCode": mtx_dseg}, egd   )  # Egress (used for Walk-Transit-KNR drive from transit time)

# Read user inputs from Visum
proj_dir = Visum.GetPath(2)

# Pull "Code" field from procedure sequence containing Code, DSegCode, and filename
procedure_code = Visum.Procedures.OperationExecutor.GetCurrentOperation().AttValue("CODE")   # Example: outputs a string like -> '[["mfamsov","PuT","AM2_SOV.omx"],["mfmdMpe","PuT","MD1_MPE.omx"]]'
procedure_codes = eval(procedure_code)   # Example: outputs a list of lists like -> [["mfamsov","PuT","AM2_SOV.omx"],["mfmdMpe","PuT","MD1_MPE.omx"]]

# Loop thru each matrix set in the "Code" field and export
for x in range(len(procedure_codes)):
    dsegcode = procedure_codes[x][0]
    knr_flag = procedure_codes[x][1]

putskim_postprocessing(dsegcode,knr_flag)

