# Export OMX files from LCOG model based on "Code" field in Procedure Sequence
# 4/29/2025 - Luke Gordon (RSG)
# Adapted from code from Chetan Joshi (PTV)

import tables
import numpy as np
import pandas as pd
import os
import VisumPy.helpers as h
import openmatrix as omx



def omx_export(x, mtx_code, corename, mtx_dseg, omx_fn):
    
    
    # Below exports the matrices as OMX files succesfully
    # Pull matrix out but close .omx file if there is an error
    omx_file = omx.open_file(omx_fn, 'a')
    try:
        mx = h.GetMatrixRaw(Visum, {"CODE": mtx_code , "DSegCode": mtx_dseg})
    except Exception as e:
        print(f"Error getting matrix for CODE={mtx_code}, DSegCode={mtx_dseg}: {e}")
        omx_file.close()

    core_name = corename
    # Delete the core if it already exists
    if core_name in omx_file:
        del omx_file[core_name]


    omx_file[core_name] = mx.astype(np.float32)

    # Create mapping to TAZ numbers
    zones = np.array(h.GetMulti(Visum.Net.Zones,r"NO", activeOnly = True))
    taz_equivs = np.arange(1, len(zones) + 1)                  # 1-number of zones inclusive

    try:
        omx_file.create_mapping('taz', taz_equivs)
        omx_file.close()
    except Exception as e:
        omx_file.close()
    


# Read user inputs from Visum
proj_dir = Visum.GetPath(2)

# Pull "Code" field from procedure sequence containing Code, DSegCode, and filename
procedure_code = Visum.Procedures.OperationExecutor.GetCurrentOperation().AttValue("CODE")   # Example: outputs a string like -> '[["mfamsov","PuT","AM2_SOV.omx"],["mfmdMpe","PuT","MD1_MPE.omx"]]'
procedure_codes = eval(procedure_code)   # Example: outputs a list of lists like -> [["mfamsov","PuT","AM2_SOV.omx"],["mfmdMpe","PuT","MD1_MPE.omx"]]

# Delete omx file if it exists
filename = procedure_codes[0][3]
if os.path.exists(filename):
    os.remove(filename)


# Loop thru each matrix set in the "Code" field and export
for x in range(len(procedure_codes)):
    code     = procedure_codes[x][0]
    core     = procedure_codes[x][1]
    dsegcode = procedure_codes[x][2]
    filename = procedure_codes[x][3]


    omx_export(x, code, core, dsegcode, proj_dir + filename)

