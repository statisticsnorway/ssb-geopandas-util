# %%
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


src = str(Path(__file__).parent).strip("tests") + "src"

sys.path.insert(0, src)

import sgis as sg


def test_network_analysis(points_oslo, roads_oslo):
    warnings.filterwarnings(action="ignore", category=FutureWarning)
    #    warnings.filterwarnings(action="ignore", category=UserWarning)
    pd.options.mode.chained_assignment = None

    split_lines = False

    ### READ FILES

    p = points_oslo
    p = sg.clean_clip(p, p.geometry.iloc[0].buffer(700))
    p["idx"] = p.index
    p["idx2"] = p.index

    r = roads_oslo
    r = sg.clean_clip(r, p.geometry.loc[0].buffer(750))

    def run_analyses(nwa, p):
        x = nwa.get_route_frequencies(p.loc[p.idx == 0], p.sample(7))
        assert len(x.columns) > 5, len(x.columns)

        if __name__ == "__main__":
            sg.qtm(x, "frequency")

        ### OD COST MATRIX

        for search_factor in [0, 50]:
            nwa.rules.search_factor = search_factor
            od = nwa.od_cost_matrix(p, p)

        assert list(od.columns) == ["origin", "destination", nwa.rules.weight]

        nwa.rules.search_factor = 10

        for search_tolerance in [100, 1000]:
            nwa.rules.search_tolerance = search_tolerance
            od = nwa.od_cost_matrix(p, p)
        assert list(od.columns) == ["origin", "destination", nwa.rules.weight]

        print(
            nwa.log[
                ["search_tolerance", "search_factor", "percent_missing", "cost_mean"]
            ]
        )

        assert all(nwa.log["percent_missing"] == 0)
        assert all(nwa.log["cost_mean"] < 3)
        assert all(nwa.log["cost_mean"] > 0)

        od = nwa.od_cost_matrix(p, p, lines=True)
        assert list(od.columns) == [
            "origin",
            "destination",
            nwa.rules.weight,
            "geometry",
        ]

        p1 = nwa.origins.gdf
        p1 = p1.loc[[p1.missing.idxmin()]].sample(1).idx.values[0]

        if __name__ == "__main__":
            sg.qtm(od.loc[od.origin == p1], nwa.rules.weight, scheme="quantiles")

        od = nwa.od_cost_matrix(p, p, rowwise=True)
        assert len(od) == len(p)
        assert list(od.columns) == ["origin", "destination", nwa.rules.weight]

        ### GET ROUTE

        sp = nwa.get_route(p, p)
        assert list(sp.columns) == [
            "origin",
            "destination",
            nwa.rules.weight,
            "geometry",
        ]

        sp = nwa.get_route(p.loc[[349]], p)

        nwa.rules.search_factor = 0
        nwa.rules.split_lines = False

        sp = nwa.get_route(p.loc[[349]], p.loc[[440]])
        if __name__ == "__main__":
            sg.qtm(sp)
        nwa.rules.split_lines = True
        sp = nwa.get_route(p.loc[[349]], p.loc[[440]])
        if __name__ == "__main__":
            sg.qtm(sp)
        sp = nwa.get_route(p.loc[[349]], p.loc[[440]])
        if __name__ == "__main__":
            sg.qtm(sp)

        nwa.rules.split_lines = False
        sp = nwa.get_route(p.loc[[349]], p)
        if __name__ == "__main__":
            sg.qtm(sp)
        nwa.rules.split_lines = True
        sp = nwa.get_route(p.loc[[349]], p)
        if __name__ == "__main__":
            sg.qtm(sp)

        assert list(sp.columns) == [
            "origin",
            "destination",
            nwa.rules.weight,
            "geometry",
        ]
        sp = nwa.get_route(p.loc[[349]], p)
        if __name__ == "__main__":
            sg.qtm(sp)

        ### GET ROUTE FREQUENCIES
        print(len(p))
        print(len(p))
        print(len(p))
        sp = nwa.get_route_frequencies(p.loc[[349]], p)
        if __name__ == "__main__":
            sg.qtm(sp)

        ### SERVICE AREA

        sa = nwa.service_area(p, breaks=5, dissolve=False)

        print(len(sa))

        sa = sa.drop_duplicates(["source", "target"])

        print(len(sa))
        if __name__ == "__main__":
            sg.qtm(sa)

        sa = nwa.service_area(p.loc[[349]], breaks=np.arange(1, 11))
        print(sa.columns)
        sa = sa.sort_values("minutes", ascending=False)
        if __name__ == "__main__":
            sg.qtm(sa, "minutes", k=10)
        assert list(sa.columns) == [
            "origin",
            nwa.rules.weight,
            "geometry",
        ]
        ### GET K ROUTES

        for x in [0, 100]:
            sp = nwa.get_k_routes(
                p.loc[[349]], p.loc[[440]], k=5, drop_middle_percent=x
            )
            if __name__ == "__main__":
                sg.qtm(sp, "k")

        assert list(sp.columns) == [
            "origin",
            "destination",
            nwa.rules.weight,
            "k",
            "geometry",
        ], list(sp.columns)

        n = 0
        for x in [-1, 101]:
            try:
                sp = nwa.get_k_routes(
                    p.loc[[349]],
                    p.loc[[440]],
                    k=5,
                    drop_middle_percent=x,
                )
                if __name__ == "__main__":
                    sg.qtm(sp, "k")
            except ValueError:
                n += 1
                print("drop_middle_percent works as expected", x)

        assert n == 2

        sp = nwa.get_k_routes(p.loc[[349]], p.loc[[440]], k=5, drop_middle_percent=50)
        print(sp)
        if __name__ == "__main__":
            sg.qtm(sp)

        sp = nwa.get_k_routes(p.loc[[349]], p, k=5, drop_middle_percent=50)
        if __name__ == "__main__":
            sg.qtm(sp)

    ### MAKE THE ANALYSIS CLASS
    nw = (
        sg.DirectedNetwork(r)
        .make_directed_network_norway(minute_cols=("drivetime_fw", "drivetime_bw"))
        .remove_isolated()
    )

    rules = sg.NetworkAnalysisRules(
        weight="minutes",
        split_lines=split_lines,
    )

    nwa = sg.NetworkAnalysis(nw, rules=rules)
    print(nwa)

    run_analyses(nwa, p)

    nw = sg.DirectedNetwork(r).make_directed_network_norway().remove_isolated()

    rules = sg.NetworkAnalysisRules(
        weight="minutes",
        split_lines=split_lines,
    )

    nwa = sg.NetworkAnalysis(nw, rules=rules)
    print(nwa)

    run_analyses(nwa, p)


def main():
    roads_oslo = sg.read_parquet_url(
        "https://media.githubusercontent.com/media/statisticsnorway/ssb-sgis/main/tests/testdata/roads_oslo_2022.parquet"
    )
    points_oslo = sg.read_parquet_url(
        "https://media.githubusercontent.com/media/statisticsnorway/ssb-sgis/main/tests/testdata/points_oslo.parquet"
    )

    test_network_analysis(points_oslo, roads_oslo)


if __name__ == "__main__":
    # import cProfile
    # cProfile.run("main()", sort="cumtime")
    main()

# %%
