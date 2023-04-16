import warnings

import numpy as np
import pandas as pd
from geopandas import GeoDataFrame
from igraph import Graph
from pandas import DataFrame


def _get_route(
    graph: Graph,
    weight: str,
    roads: GeoDataFrame,
    od_pairs: pd.MultiIndex,
) -> GeoDataFrame:
    """Function used in the get_route method of NetworkAnalysis."""

    warnings.filterwarnings("ignore", category=RuntimeWarning)

    resultlist: list[DataFrame] = []

    for ori_id, des_id in od_pairs:
        indices = _get_one_route(graph, ori_id, des_id)

        if not indices:
            continue

        line_ids = _create_line_id_df(indices["source_target_weight"], ori_id, des_id)

        resultlist.append(line_ids)

    if not resultlist:
        warnings.warn(
            "No paths were found. Try larger search_tolerance or search_factor. "
            "Or close_network_holes() or remove_isolated()."
        )
        return pd.DataFrame(columns=["origin", "destination", weight, "geometry"])

    results: DataFrame = pd.concat(resultlist)
    assert list(results.columns) == ["origin", "destination"], list(results.columns)
    lines: GeoDataFrame = _get_line_geometries(results, roads, weight)
    lines = lines.dissolve(by=["origin", "destination"], aggfunc="sum", as_index=False)

    return lines[["origin", "destination", weight, "geometry"]]


def _get_k_routes(
    graph: Graph,
    weight: str,
    roads: GeoDataFrame,
    k: int,
    drop_middle_percent: int,
    od_pairs: pd.MultiIndex,
) -> GeoDataFrame:
    """Function used in the get_k_routes method of NetworkAnalysis."""
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    resultlist: list[DataFrame] = []

    for ori_id, des_id in od_pairs:
        k_lines: DataFrame = _loop_k_routes(
            graph, ori_id, des_id, k, drop_middle_percent
        )
        if k_lines is not None:
            resultlist.append(k_lines)

    if not resultlist:
        warnings.warn(
            "No paths were found. Try larger search_tolerance or search_factor. "
            "Or close_network_holes() or remove_isolated()."
        )
        return pd.DataFrame(columns=["origin", "destination", weight, "geometry"])

    results: DataFrame = pd.concat(resultlist)
    assert list(results.columns) == ["origin", "destination", "k"], list(
        results.columns
    )
    lines: GeoDataFrame = _get_line_geometries(results, roads, weight)

    lines = lines.dissolve(
        by=["origin", "destination", "k"], aggfunc="sum", as_index=False
    )

    return lines[["origin", "destination", weight, "k", "geometry"]]


def _get_route_frequencies(
    graph,
    roads: GeoDataFrame,
    weight_df: DataFrame,
):
    """Function used in the get_route_frequencies method of NetworkAnalysis."""
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    resultlist: list[DataFrame] = []

    for ori_id, des_id in weight_df.index:
        indices = _get_one_route(graph, ori_id, des_id)

        if not indices:
            continue

        line_ids = DataFrame({"source_target_weight": indices["source_target_weight"]})
        line_ids["origin"] = ori_id
        line_ids["destination"] = des_id
        line_ids["multiplier"] = weight_df.loc[ori_id, des_id].iloc[0]

        resultlist.append(line_ids)

    summarised = (
        pd.concat(resultlist, ignore_index=True)
        .groupby("source_target_weight")["multiplier"]
        .sum()
    )

    roads["frequency"] = roads["source_target_weight"].map(summarised)

    roads_visited = roads.loc[roads.frequency.notna()].drop(
        "source_target_weight", axis=1
    )

    return roads_visited


def _get_one_route(graph: Graph, ori_id: str, des_id: str):
    """Get the edges for one route."""
    res = graph.get_shortest_paths(
        weights="weight", v=ori_id, to=des_id, output="epath"
    )
    if not res[0]:
        return []

    return graph.es[res[0]]


def _get_line_geometries(line_ids, roads, weight) -> GeoDataFrame:
    road_mapper = roads.set_index(["source_target_weight"])[[weight, "geometry"]]
    line_ids = line_ids.join(road_mapper)
    return GeoDataFrame(line_ids, geometry="geometry", crs=roads.crs)


def _create_line_id_df(source_target_weight: list, ori_id, des_id) -> DataFrame:
    line_ids = DataFrame(index=source_target_weight)

    # remove edges from ori/des to the roads
    line_ids = line_ids.loc[~line_ids.index.str.endswith("_0")]

    line_ids["origin"] = ori_id
    line_ids["destination"] = des_id

    return line_ids


def _loop_k_routes(graph: Graph, ori_id, des_id, k, drop_middle_percent) -> DataFrame:
    """Workaround for igraph's get_k_shortest_paths.

    igraph's get_k_shorest_paths doesn't seem to work (gives just the same path k
    times), so doing it manually. Run _get_one_route, then remove the edges in the
    middle of the route, given with drop_middle_percent, repeat k times.
    """
    graph = graph.copy()

    lines: list[DataFrame] = []

    for i in range(k):
        indices = _get_one_route(graph, ori_id, des_id)

        if not indices:
            continue

        line_ids = _create_line_id_df(indices["source_target_weight"], ori_id, des_id)
        line_ids["k"] = i + 1
        lines.append(line_ids)

        edge_tuples = indices["edge_tuples"]

        n_edges_to_keep = (
            len(edge_tuples) - len(edge_tuples) * drop_middle_percent / 100
        ) / 2

        n_edges_to_keep = int(round(n_edges_to_keep, 0))

        if n_edges_to_keep == 0:
            n_edges_to_keep = 1

        to_be_dropped = edge_tuples[n_edges_to_keep:-n_edges_to_keep]
        graph.delete_edges(to_be_dropped)

    if lines:
        return pd.concat(lines)
    else:
        return pd.DataFrame()
