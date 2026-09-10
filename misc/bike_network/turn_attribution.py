import pandas as pd

# Load files
mpo = "SKATS" # SKATS
turns_file = f"LinkNodeTurns_{mpo}/TurnsWork.xlsx"
output_file = f"LinkNodeTurns_{mpo}/turns.csv"
turns = pd.read_excel(turns_file)

# Drop existing columns
turns = turns.drop(columns = ["USLT", 'USCR'])

# Define functions
# TYPENO definition: 
# 1 = right turn; 2 = thru; 3 = left; 4 = u-turn
def code_uslt(row):
    if row["ISTURN"] == 1:
        if row["VIANODE\SIGNAL"] == 0:  #  unsignalized
            if row["TYPENO"] == 3:  # left turn
                if row["FROMLINK\REVERSELINK\TRAFFCAT"] == 2 or row["FROMLINK\REVERSELINK\TRAFFCAT"] == 3:
                    return 2
                elif row["FROMLINK\REVERSELINK\TRAFFCAT"] == 1:
                    return 1
    
def code_uscr(row):
    if row["ISTURN"] == 1:
        if row["VIANODE\SIGNAL"] == 0:  # unsignalized
            if row["TYPENO"] == 1:  # right turn
                if row["TOLINK\TRAFFCAT"] >= 1:
                    return 1
            if row["TYPENO"] == 2 or row["TYPENO"] ==3:   # thru, left
                if row["TOLINK\TRAFFCAT"] == 1:
                    return 2
                elif row["TOLINK\TRAFFCAT"] > 1:
                    return 3

# Code USLT and USCR
turns["USLT"] = turns.apply(code_uslt, axis = 1).fillna(0)
turns["USCR"] = turns.apply(code_uscr, axis = 1).fillna(0)

# Checks
print(turns["USLT"].value_counts())
print(turns["USCR"].value_counts())

# Export
turns.to_csv(output_file, ignore_index = True)