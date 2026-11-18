"""White Christmas: ERA5-Land snow statistics pipeline."""

import os as _os
from importlib.util import find_spec as _find_spec

__version__ = "0.1.0"


def _use_bundled_geo_data() -> None:
    """Point PROJ and GDAL at the data shipped with the rasterio wheel.

    Other installs (PostGIS, QGIS) often set PROJ_LIB/GDAL_DATA globally to an incompatible
    proj.db, which breaks CRS lookups ("EPSG code is unknown").
    """
    spec = _find_spec("rasterio")
    if not spec or not spec.submodule_search_locations:
        return
    base = list(spec.submodule_search_locations)[0]
    proj = _os.path.join(base, "proj_data")
    gdal = _os.path.join(base, "gdal_data")
    if _os.path.isdir(proj):
        _os.environ["PROJ_DATA"] = proj
        _os.environ["PROJ_LIB"] = proj
    if _os.path.isdir(gdal):
        _os.environ["GDAL_DATA"] = gdal


_use_bundled_geo_data()
