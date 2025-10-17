import pandas as pd
import matplotlib.pyplot as plt

from hydrobricks import Model
from hydrobricks.forcing import Forcing
from hydrobricks.structures import Lumped  # simple structure
from hydrobricks.parameters import Param  # parameter container

# 1. Define forcing (rainfall time series)
# Make a simple DataFrame with datetime index and a “precip” column
times = pd.date_range("2000-01-01", periods=25, freq="H")
precip = [0.0]*5 + [1.0]*10 + [0.0]*10  # e.g. a pulse of rainfall in the middle
df = pd.DataFrame({"precip": precip}, index=times)

forcing = Forcing(dataframe=df, precip="precip")

# 2. Choose a structure (a “lumped” model for whole catchment)
# Lumped means the catchment is treated as a single unit
structure = Lumped()

# 3. Parameterize model
# Here we create a Param object and set parameters; parameter names depend on model type
params = Param()
# Suppose the model uses 'CN' (curve number), 'Ksat' (saturated conductivity), etc.
# I'm just picking example parameters; you'll need to adapt to the structure's param names.
params["CN"] = 75.0
params["Ksat"] = 0.1

# 4. Build the model
model = Model(structure=structure, parameters=params, forcing=forcing)

# 5. Run the model
outputs = model.run()

# 6. Inspect / plot outputs
# outputs is often a DataFrame or dict of fluxes etc.
print(outputs.head())

# Plot e.g. discharge over time (if “Q” is an output)
if "Q" in outputs.columns:
    plt.figure(figsize=(8, 4))
    outputs["Q"].plot(title="Simulated Discharge (Q)")
    plt.ylabel("Flow (units)")
    plt.xlabel("Time")
    plt.tight_layout()
    plt.show()

