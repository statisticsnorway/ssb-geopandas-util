#%%
import warnings
import numpy as np
import geopandas as gpd
import gis_utils as gs
from pathlib import Path


def test_service_area():

    p = gpd.read_parquet(Path(__file__).parent / "testdata" / "random_points.parquet")
    p["idx"] = p.index
    p["idx2"] = p.index
    
    r = gpd.read_parquet(Path(__file__).parent / "testdata" / "roads_oslo_2022.parquet")
    
    nw = (
        gs.DirectedNetwork(r)
        .make_directed_network_norway()
        .remove_isolated()
    )

    nwa = gs.NetworkAnalysis(nw, cost="minutes")

    sa = nwa.service_area(p.sample(25), impedance=5, dissolve=False)

    print(len(sa))

    sa = sa.drop_duplicates(["source", "target"])

    print(len(sa))
    gs.qtm(sa)

    # many impedances
    sa = nwa.service_area(p.iloc[[0]], impedance=np.arange(1, 11), id_col="idx")
    sa = sa.sort_values("minutes", ascending=False)
    gs.qtm(sa, "minutes", k=10)


def main():
    test_service_area()


if __name__ == "__main__":
    main()