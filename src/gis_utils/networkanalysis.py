from typing import Tuple

import igraph
import numpy as np
from geopandas import GeoDataFrame
from igraph import Graph
from pandas import DataFrame

from .directednetwork import DirectedNetwork
from .geopandas_utils import push_geom_col
from .network import Network
from .networkanalysisrules import NetworkAnalysisRules
from .od_cost_matrix import od_cost_matrix
from .points import EndPoints, StartPoints
from .service_area import service_area
from .shortest_path import shortest_path


class NetworkAnalysis:
    """Class that holds the actual network analysis methods.

    Args:
        network: either the base Network class or a subclass, chiefly the DirectedNetwork class.
            The network should be customized beforehand, but can also be accessed through
            the 'network' attribute of this class.
        weight: e.i. 'minutes' or 'meters'. Or custom numeric column.
        search_tolerance: meters.
        search_factor: .
        weight_to_nodes: .

    Example:

    roads = gpd.GeoDataFrame(filepath_roads)
    points = gpd.GeoDataFrame(filepath_points)

    # the data should have crs with meters as units, e.g. UTM:
    roads = roads.to_crs(25833)
    points = points.to_crs(25833)

    nw = (
        DirectedNetwork(roads)
        .make_directed_network_osm()
        .remove_isolated()
        )

    nwa = NetworkAnalysis(nw, weight="minutes")

    od = nwa.od_cost_matrix(p, p)

    """

    def __init__(
        self,
        network: Network | DirectedNetwork,
        rules: NetworkAnalysisRules,
    ):
        self.network = network
        self.rules = rules

        if not isinstance(rules, NetworkAnalysisRules):
            raise ValueError(
                f"'rules' should be of type NetworkAnalysisRules. Got {type(rules)}"
            )

        if not isinstance(network, (Network, DirectedNetwork)):
            raise ValueError(
                f"'network' should of type DirectedNetwork or Network. Got {type(network)}"
            )

        self.network.gdf = self.rules.validate_weight(
            self.network.gdf, raise_error=False
        )

        self.update_point_wkts()
        self.rules.update_rules()

    def od_cost_matrix(
        self,
        startpoints: GeoDataFrame,
        endpoints: GeoDataFrame,
        id_col: str | Tuple[str, str] | None = None,
        lines: bool = False,
        **kwargs,
    ) -> DataFrame | GeoDataFrame:
        self.prepare_network_analysis(startpoints, endpoints, id_col)

        results = od_cost_matrix(
            graph=self.graph,
            startpoints=self.startpoints.gdf,
            endpoints=self.endpoints.gdf,
            weight=self.rules.weight,
            lines=lines,
            **kwargs,
        )

        self.startpoints.get_n_missing(results, "origin")
        self.endpoints.get_n_missing(results, "destination")

        if id_col:
            results["origin"] = results["origin"].map(self.startpoints.id_dict)
            results["destination"] = results["destination"].map(self.endpoints.id_dict)

        if lines:
            results = push_geom_col(results)

        return results

    def shortest_path(
        self,
        startpoints: GeoDataFrame,
        endpoints: GeoDataFrame,
        id_col: str | Tuple[str, str] | None = None,
        summarise: bool = False,
        **kwargs,
    ) -> GeoDataFrame:
        self.prepare_network_analysis(startpoints, endpoints, id_col)

        results = shortest_path(
            graph=self.graph,
            startpoints=self.startpoints.gdf,
            endpoints=self.endpoints.gdf,
            weight=self.rules.weight,
            roads=self.network.gdf,
            summarise=summarise,
            **kwargs,
        )

        if not summarise:
            self.startpoints.get_n_missing(results, "origin")
            self.endpoints.get_n_missing(results, "destination")

        if id_col and not summarise:
            results["origin"] = results["origin"].map(self.startpoints.id_dict)
            results["destination"] = results["destination"].map(self.endpoints.id_dict)

        results = push_geom_col(results)

        return results

    def service_area(
        self, startpoints: GeoDataFrame, id_col: str | None = None, **kwargs
    ) -> GeoDataFrame:
        self.prepare_network_analysis(startpoints, id_col=id_col)

        results = service_area(
            self.graph,
            self.startpoints.gdf,
            self.rules.weight,
            self.network.gdf,
            **kwargs,
        )

        if id_col:
            results[id_col] = results["origin"].map(self.startpoints.id_dict)
            results = results.drop("origin", axis=1)

        results = push_geom_col(results)

        return results

    def prepare_network_analysis(
        self, startpoints, endpoints=None, id_col: str | None = None
    ) -> None:
        """Prepares the weight column, node ids and start- and endpoints.
        Also updates the graph if it is not yet created and no parts of the analysis has changed.
        this method is run inside od_cost_matrix, shortest_path and service_area.
        """

        self.network.gdf = self.rules.validate_weight(
            self.network.gdf, raise_error=True
        )

        self.startpoints = StartPoints(
            startpoints,
            id_col=id_col,
            temp_idx_start=max(self.network.nodes.node_id.astype(int)) + 1,
        )

        if endpoints is not None:
            self.endpoints = EndPoints(
                endpoints,
                id_col=id_col,
                temp_idx_start=max(self.startpoints.gdf.temp_idx.astype(int)) + 1,
            )

        else:
            self.endpoints = None

        if not (self.graph_is_up_to_date() and self.network.nodes_are_up_to_date()):
            self.network.update_nodes_if()

            edges, weights = self.get_edges_and_weights()

            self.graph = self.make_graph(
                edges=edges, weights=weights, directed=self.network.directed
            )

            self.add_missing_vertices()

        self.update_point_wkts()
        self.rules.update_rules()

    def get_edges_and_weights(self) -> Tuple[list[Tuple[str, ...]], list[float]]:
        """Creates lists of edges and weights which will be used to make the graph.
        Edges and weights between startpoints and nodes and nodes and endpoints are also added.
        """

        edges = [
            (str(source), str(target))
            for source, target in zip(
                self.network.gdf["source"], self.network.gdf["target"]
            )
        ]

        weights = list(self.network.gdf[self.rules.weight])

        edges_start, weights_start = self.startpoints.get_edges_and_weights(
            self.network.nodes, self.rules
        )
        edges = edges + edges_start
        weights = weights + weights_start

        if self.endpoints is None:
            return edges, weights

        edges_end, weights_end = self.endpoints.get_edges_and_weights(
            self.network.nodes, self.rules
        )
        edges = edges + edges_end
        weights = weights + weights_end

        return edges, weights

    def add_missing_vertices(self):
        """Adds the points that had no nodes within the search_tolerance
        to the graph. To prevent error when running the distance calculation.
        """
        self.graph.add_vertices(
            [
                idx
                for idx in self.startpoints.gdf["temp_idx"]
                if idx not in self.graph.vs["name"]
            ]
        )
        if self.endpoints is not None:
            self.graph.add_vertices(
                [
                    idx
                    for idx in self.endpoints.gdf["temp_idx"]
                    if idx not in self.graph.vs["name"]
                ]
            )

    @staticmethod
    def make_graph(
        edges: list[Tuple[str, ...]] | np.ndarray[Tuple[str, ...]],
        weights: list[float] | np.ndarray[float],
        directed: bool,
    ) -> Graph:
        """Creates an igraph Graph from a list of edges and weights."""

        assert len(edges) == len(weights)

        graph = igraph.Graph.TupleList(edges, directed=directed)

        graph.es["weight"] = weights

        assert min(graph.es["weight"]) >= 0

        return graph

    def graph_is_up_to_date(self) -> bool:
        """Returns False if the rules of the graphmaking has changed,
        or if the points have changed"""

        if not hasattr(self, "graph") or not hasattr(self, "wkts"):
            return False

        if self.rules.rules_have_changed():
            return False

        if self.points_have_changed(self.startpoints.gdf, what="start"):
            return False

        if self.endpoints is None:
            return True

        if self.points_have_changed(self.endpoints.gdf, what="end"):
            return False

        return True

    def points_have_changed(self, points: GeoDataFrame, what: str) -> bool:
        """This method is best stored in the NetworkAnalysis class,
        since the point classes are initialised each time an analysis is run."""
        if self.wkts[what] != [geom.wkt for geom in points.geometry]:
            return True

        if not all(x in self.graph.vs["name"] for x in list(points.temp_idx.values)):
            return True

        return False

    def update_point_wkts(self) -> None:
        """Creates a dict of wkt lists. This method is run after the graph is created.
        If the wkts haven't updated since the last run, the graph doesn't have to be remade.
        """
        self.wkts = {}

        self.wkts["network"] = [geom.wkt for geom in self.network.gdf.geometry]

        if not hasattr(self, "startpoints"):
            return

        self.wkts["start"] = [geom.wkt for geom in self.startpoints.gdf.geometry]

        if self.endpoints is not None:
            self.wkts["end"] = [geom.wkt for geom in self.endpoints.gdf.geometry]

    def __repr__(self) -> str:
        nw = f"network={self.network.__repr__()}"
        if self.rules.weight_to_nodes_dist:
            x = f", weight_to_nodes_dist={self.rules.weight_to_nodes_dist}"
        elif self.rules.weight_to_nodes_kmh:
            x = f", weight_to_nodes_dist={self.rules.weight_to_nodes_kmh}"
        elif self.rules.weight_to_nodes_mph:
            x = f", weight_to_nodes_dist={self.rules.weight_to_nodes_mph}"
        else:
            x = ", ..."

        rules = self.rules.__repr__()
        for txt in ["weight_to_nodes_", "dist", "kmh", "mph", "=None", "=False"]:
            rules = rules.replace(txt, "")
        for txt in [", )"] * 4:
            rules = rules.replace(txt, ")")
        rules = rules.replace(")", "")

        return (
            f"{self.__class__.__name__}("
            f"network={self.network.__repr__()}, "
            f"rules={rules}{x}))"
            #          f"{nw}"
            #         f"weight={self.rules.weight}, "
            #        f"search_tolerance={self.rules.search_tolerance}, "
            #       f"search_factor={self.rules.search_factor}"
            #      f"{x})"
        )
