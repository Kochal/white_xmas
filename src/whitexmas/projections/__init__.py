"""Future projections of white-Christmas probability at global warming levels (plan §3b).

Method B (D-9): for each CMIP6 model, the white-Christmas frequency is computed in the model's
own climate for a 1995-2014 baseline and for the 20-year window around +1.5, +2 and +3 °C
global warming. The change is taken in log-odds, regridded bilinearly to the ERA5-Land 0.1°
grid and applied to the ERA5-Land baseline probability (1996-2025).
"""
