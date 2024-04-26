# %%
import sys
import warnings
from pathlib import Path

import pandas as pd

src = str(Path(__file__).parent).strip("tests") + "src"

sys.path.insert(0, src)

import sgis as sg


def test_split_lines(points_oslo, roads_oslo):
    warnings.filterwarnings(action="ignore", category=FutureWarning)
    #    warnings.filterwarnings(action="ignore", category=UserWarning)
    pd.options.mode.chained_assignment = None

    ### READ FILES

    points = points_oslo
    r = roads_oslo

    r = sg.clean_clip(r, points.geometry.loc[0].buffer(700))
    points = sg.clean_clip(points, points.geometry.loc[0].buffer(700))

    ### MAKE THE ANALYSIS CLASS
    connected_roads = sg.get_connected_components(r).query("connected == 1")
    directed_roads = sg.make_directed_network_norway(connected_roads, dropnegative=True)

    rules = sg.NetworkAnalysisRules(
        directed=True,
        weight="minutes",
    )

    nwa = sg.NetworkAnalysis(directed_roads, rules=rules, detailed_log=False)
    print(nwa)

    nwa.rules.split_lines = False

    od = nwa.od_cost_matrix(points, points)
    sp1 = nwa.get_route(points.loc[[97]], points.loc[[135]])
    sp1["split_lines"] = "Not splitted"

    nwa.rules.split_lines = True

    od = nwa.od_cost_matrix(points, points)
    print(nwa.log[["method", "cost_mean", "percent_missing"]])

    # the split lines should be reset after the analysis
    # repeat to see if the unsplitting happens
    for _ in range(3):
        sp2 = nwa.get_route(points.loc[[97]], points.loc[[135]])
    sp2["split_lines"] = "Splitted"

    assert sp1[rules.weight].sum() != sp2[rules.weight].sum()
    assert sp1[rules.weight].sum() < sp2[rules.weight].sum() * 0.7

    if __name__ == "__main__":
        sg.qtm(sp1, sp2, column="split_lines", cmap="bwr")


def main():
    from oslo import points_oslo
    from oslo import roads_oslo

    test_split_lines(points_oslo(), roads_oslo())


if __name__ == "__main__":

    # cProfile.run("main()", sort="cumtime")
    main()
