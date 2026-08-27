import pandas as pd

df = pd.read_csv(
    "personas_censo2024.csv",
    sep=";",
    usecols=["comuna"]
)

poblacion = (
    df.groupby("comuna")
      .size()
      .reset_index(name="personas")
      .rename(columns={"comuna": "CUT"})
)

poblacion["CUT"] = poblacion["CUT"].astype(int)

poblacion.to_csv(
    "poblacion_comunas_censo2024.csv",
    index=False
)
