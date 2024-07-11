import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

src = str(Path(__file__).parent).replace("tests", "") + "src"


sys.path.insert(0, src)

import sgis as sg


def test_debug_config():
    """Make sure that debug config is not set when pushing to github."""
    center = sg.debug_config._DEBUG_CONFIG["center"]
    assert isinstance(center, sg.debug_config._NoExplore), type(center)
