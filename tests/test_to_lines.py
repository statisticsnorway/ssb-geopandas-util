#%%
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon


src = str(Path(__file__).parent.parent) + "/src"

sys.path.insert(0, src)

import sgis as sg


def test_to_lines():
    poly1 = sg.to_gdf(Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]))

    inner_poly = sg.to_gdf(
        Polygon([(0.25, 0.25), (0.25, 0.75), (0.75, 0.75), (0.75, 0.25)])
    )

    poly1_diff = poly1.overlay(inner_poly, how="difference")

    lines = sg.to_lines(poly1_diff)
    lines["l"] = lines.length.astype(str)
    sg.qtm(lines, "l", legend_title=len(lines))
    assert len(lines) > 1

    poly2 = sg.to_gdf(Polygon([(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)]))

    sg.qtm(poly1, poly2, inner_poly)

    lines = sg.to_lines(poly1, poly2, inner_poly)
    lines["l"] = lines.length.astype(str)
    sg.qtm(lines, "l", legend_title=len(lines))

    lines = sg.to_lines(poly1, poly2)
    lines["l"] = lines.length.astype(str)
    sg.qtm(lines, "l", legend_title=len(lines))

    lines = sg.to_lines(poly1, poly2, inner_poly, poly2)
    lines["l"] = lines.length.astype(str)
    sg.qtm(lines, "l", legend_title=len(lines))


def main():
    test_to_lines()


if __name__ == "__main__":
    main()


import sgis as sg
from shapely.geometry import Polygon

poly1 = sg.to_gdf(Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]))
poly1["poly1"] = 1
poly2 = sg.to_gdf(Polygon([(0.5, 0.5), (0.5, 1.5), (1.5, 1.5), (1.5, 0.5)]))
poly2["poly2"] = 1
lines = sg.to_lines(poly1, poly2)
lines
sg.qtm(poly1, poly2)
lines["l"] = lines.length.astype(str)
sg.qtm(lines, "l")
