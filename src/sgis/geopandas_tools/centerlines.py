import functools
import warnings

import numpy as np
import pandas as pd
import shapely
from geopandas import GeoDataFrame, GeoSeries
from geopandas.array import GeometryArray
from numpy.typing import NDArray
from shapely import (
    STRtree,
    distance,
    extract_unique_points,
    get_parts,
    get_rings,
    line_merge,
    make_valid,
    segmentize,
    unary_union,
    voronoi_polygons,
)
from shapely.errors import GEOSException
from shapely.geometry import LineString
from shapely.ops import nearest_points

from ..maps.maps import explore, explore_locals
from ..networkanalysis.traveling_salesman import traveling_salesman_problem
from .conversion import to_gdf, to_geoseries
from .general import clean_geoms, make_lines_between_points, sort_long_first
from .geometry_types import make_all_singlepart
from .sfilter import sfilter_inverse, sfilter_split


warnings.simplefilter(action="ignore", category=FutureWarning)


def get_traveling_salesman_lines(df, return_to_start=False):
    path = traveling_salesman_problem(df, return_to_start=return_to_start)

    try:
        return [LineString([p1, p2]) for p1, p2 in zip(path[:-1], path[1:])]
    except IndexError as e:
        if len(path) == 1:
            return path
        raise e


def remove_longest_if_not_intersecting(centerlines, geoms):
    centerlines = sort_long_first(make_all_singlepart(centerlines))

    has_only_one_line = centerlines.groupby(level=0).size() == 1
    only_one_line = centerlines[has_only_one_line]
    centerlines = centerlines[~has_only_one_line]

    longest = centerlines.loc[lambda x: ~x.index.duplicated()]
    not_longest = centerlines.loc[lambda x: x.index.duplicated()]

    longest_endpoints = longest.boundary.explode(index_parts=False).sort_index()

    nearest = longest_endpoints.groupby(level=0).apply(
        lambda x: nearest_points(
            x, not_longest[not_longest.index.isin(x.index)].unary_union
        )[1]
    )
    longest_endpoints.loc[:] = make_lines_between_points(
        longest_endpoints.values, nearest.values
    )

    return pd.concat([only_one_line, not_longest, longest_endpoints])


def get_rough_centerlines(
    gdf: GeoDataFrame,
    max_segment_length: int,
) -> GeoDataFrame:
    """Get a cheaply calculated centerline of a polygon.

    The line is not guaraneteed to be completely within the polygon. The line
    should start and end at the polygons' "endpoints".

    The function is meant for getting centerlines from slivers in coverage_clean and
    snap_polygons. It will give weird results and be extremely slow for
    complext polygons like (buffered) road networks.

    """

    PRECISION = 0.01

    if not len(gdf):
        return gdf

    if not gdf.index.is_unique:
        raise ValueError("Index must be unique")

    geoms: GeoSeries = to_geoseries(gdf).explode(index_parts=False)

    segmentized: GeoSeries = segmentize(geoms, max_segment_length=max_segment_length)

    points: GeoSeries = get_points_in_polygons(segmentized, PRECISION)

    has_no_points = geoms.loc[(~geoms.index.isin(points.index))]

    more_points: GeoSeries = get_points_in_polygons(
        has_no_points.buffer(PRECISION), PRECISION
    )

    # Geometries that have no lines inside, might be perfect circles.
    # These can get the centroid as centerline
    still_has_no_points = has_no_points.loc[
        (~has_no_points.index.isin(more_points.index))
    ]
    still_has_no_points.loc[:] = geoms.loc[still_has_no_points.index].centroid

    # very thin slivers
    has_points_now = has_no_points.loc[(has_no_points.index.isin(more_points.index))]

    if len(has_points_now):
        segmentized = pd.concat(
            [
                segmentized.loc[
                    ~segmentized.index.isin(
                        still_has_no_points.index.union(has_points_now.index)
                    )
                ],
                has_points_now,
            ]
        )
    else:
        segmentized = segmentized.loc[
            ~segmentized.index.isin(still_has_no_points.index)
        ]

    # make sure to include the endpoints
    endpoints = get_approximate_polygon_endpoints(segmentized)

    geoms = geoms.loc[~geoms.index.isin(still_has_no_points.index)]

    # check if line between endpoints make up a decent centerline
    has_two = endpoints.groupby(level=0).size() == 2
    endpoint1 = endpoints.loc[has_two].groupby(level=0).first()
    endpoint2 = endpoints.loc[has_two].groupby(level=0).last()
    assert (endpoint1.index == endpoint2.index).all()

    end_to_end = GeoSeries(
        make_lines_between_points(endpoint1, endpoint2), index=endpoint1.index
    )

    # keep lines 90 percent intersecting the polygon
    length_now = end_to_end.length
    end_to_end = (
        end_to_end.intersection(geoms.buffer(PRECISION))
        .dropna()
        .loc[lambda x: x.length > length_now * 0.9]
    )

    # straight end buffer to remove all in between ends
    to_be_erased = points.index.isin(end_to_end.index)

    dont_intersect = sfilter_inverse(
        points.iloc[to_be_erased], end_to_end.buffer(PRECISION, cap_style=2)
    )

    points = (
        clean_geoms(
            pd.concat(
                [
                    points.iloc[~to_be_erased],
                    dont_intersect,
                ]
            )
        )
        .buffer(0.1)
        .groupby(level=0)
        .agg(unary_union)
        .explode(index_parts=False)
        .centroid
    )
    points = pd.concat(
        [
            points,
            endpoints,
        ]
    )

    explore(points=to_gdf(points, 25833), gdf=gdf)

    remove_longest = functools.partial(remove_longest_if_not_intersecting, geoms=geoms)

    centerlines = GeoSeries(
        points.groupby(level=0).apply(get_traveling_salesman_lines).explode()
    ).pipe(remove_longest)

    # centerlines = sort_long_first(centerlines).loc[lambda x: x.index.duplicated()]

    # fix sharp turns by using the centroids of the centerline
    centerlines2 = GeoSeries(
        (
            pd.concat(
                [
                    centerlines.centroid,
                    endpoints,
                ]
            )
            .groupby(level=0)
            .apply(get_traveling_salesman_lines)
        ).explode()
    ).pipe(remove_longest)

    centerlines3 = GeoSeries(
        (
            pd.concat(
                [
                    centerlines2.centroid,
                    endpoints,
                ]
            )
            .groupby(level=0)
            .apply(get_traveling_salesman_lines)
        ).explode()
    ).pipe(remove_longest)

    centerlines = centerlines3.groupby(level=0).agg(
        lambda x: line_merge(unary_union(x))
        # lambda x: unary_union(x)
    )

    if isinstance(gdf, GeoSeries):
        return GeoSeries(
            pd.concat([centerlines, still_has_no_points]), crs=gdf.crs
        ).sort_index()

    centerlines = GeoDataFrame(
        {"geometry": pd.concat([centerlines, still_has_no_points])}, crs=gdf.crs
    )
    return centerlines


def get_points_in_polygons(geometries: GeoSeries, precision: float) -> GeoSeries:
    # voronoi can cause problems if coordinates are nearly identical
    # buffering solves it
    try:
        voronoi_lines = voronoi_polygons(geometries, only_edges=True)
    except GEOSException:
        try:
            geometries = make_valid(geometries)
            voronoi_lines = voronoi_polygons(geometries, only_edges=True)
        except GEOSException:
            voronoi_lines = voronoi_polygons(
                geometries.buffer(precision).buffer(-precision), only_edges=True
            )

    crossing_lines = (
        geometries.buffer(precision, resolution=10)
        .intersection(voronoi_lines)
        .explode(index_parts=False)
    )
    within_polygons, not_within = sfilter_split(
        crossing_lines, geometries, predicate="within"
    )

    intersect_polys_at_two_places = (
        not_within.intersection(unary_union(get_rings(geometries))).geom_type
        == "MultiPoint"
    )
    not_within_but_relevant = not_within.loc[intersect_polys_at_two_places]

    return pd.concat([within_polygons, not_within_but_relevant]).centroid


def get_approximate_polygon_endpoints(geoms: GeoSeries) -> GeoSeries:
    out_geoms = []

    are_thin = geoms.buffer(-1e-2).is_empty
    not_thin = geoms.loc[~are_thin]
    thin = geoms.loc[are_thin].buffer(1e-2)

    rectangles = pd.concat([not_thin, thin]).minimum_rotated_rectangle()

    # get_rings returns array with integer index that must be mapped to pandas index
    rings, indices = get_rings(rectangles, return_index=True)
    int_to_pd_index = dict(enumerate(rectangles.index))
    indices = [int_to_pd_index[i] for i in indices]

    rectangles.loc[:] = (
        pd.Series(rings, index=indices).groupby(level=0).agg(unary_union)
    )
    corner_points = (
        GeoSeries(
            extract_unique_points(rectangles)
            # adding a buffer, dissolve and explode to not get two corners in same end for very thin polygons
            .buffer(0.01)
            .groupby(level=0)
            .agg(unary_union)
        )
        .explode(index_parts=False)
        .centroid
    )

    nearest_ring_point = nearest_points(
        corner_points.values, geoms.loc[corner_points.index].values
    )[1]

    distance_to_corner = pd.Series(
        distance(nearest_ring_point, corner_points), index=corner_points.index
    )

    is_two_nearest: NDArray[bool] = (
        distance_to_corner.groupby(level=0)
        .apply(lambda x: x <= x.nsmallest(2).iloc[-1])
        .values
    )

    two_nearest = pd.Series(nearest_ring_point, index=corner_points.index).iloc[
        is_two_nearest
    ]

    # geometries with more than two endpoints now, are probably crosses/star-like
    more_than_two = two_nearest.loc[lambda x: x.groupby(level=0).size() > 2]
    if len(more_than_two):
        precision = rectangles.length / 100

        two_nearest = two_nearest.loc[lambda x: ~x.index.isin(more_than_two.index)]

        by_rectangle = (
            geoms.intersection(rectangles.buffer(precision))
            .explode(index_parts=False)
            .centroid
        )

        nearest_rectangle_points = nearest_points(by_rectangle, rectangles)[1]
        nearest_geom_points = nearest_points(nearest_rectangle_points, geoms)[1]

        out_geoms.append(nearest_geom_points)

    lines_around_geometries = multipoints_to_line_segments(
        extract_unique_points(rectangles)
    )

    distance_to_rect = distance(
        two_nearest.values, rectangles.loc[two_nearest.index].values
    )

    # move the points to the rectangle
    to_be_moved = two_nearest.loc[distance_to_rect > 0.01]
    not_to_be_moved = two_nearest.loc[distance_to_rect <= 0.01]
    assert len(not_to_be_moved) + len(to_be_moved) == len(two_nearest)
    out_geoms.append(not_to_be_moved)

    if len(to_be_moved):
        tree = STRtree(lines_around_geometries.values)
        nearest_indices = tree.nearest(to_be_moved.values)

        relevant_lines_around_geometries = pd.Series(
            lines_around_geometries.iloc[nearest_indices].values,
            index=to_be_moved.index,
        )

        # then move the points to the closest vertice
        points_moved = pd.Series(
            nearest_points(
                relevant_lines_around_geometries.values,
                extract_unique_points(
                    geoms.loc[relevant_lines_around_geometries.index]
                ).values,
            )[1],
            index=to_be_moved.index,
        )
        out_geoms.append(points_moved)

    return pd.concat(out_geoms)


def multipoints_to_line_segments(
    multipoints: GeoSeries | GeoDataFrame, to_next: bool = True, cycle: bool = True
) -> GeoSeries | GeoDataFrame:
    if not len(multipoints):
        return multipoints

    multipoints = to_geoseries(multipoints)

    if isinstance(multipoints.index, pd.MultiIndex):
        index = [
            multipoints.index.get_level_values(i)
            for i in range(multipoints.index.nlevels)
        ]
        multipoints.index = pd.MultiIndex.from_arrays(
            [list(range(len(multipoints)))] + index,
            names=["range_idx"] + multipoints.index.names,
        )
    else:
        multipoints.index = pd.MultiIndex.from_arrays(
            [np.arange(0, len(multipoints)), multipoints.index],
            names=["range_idx"] + [multipoints.index.name],
        )

    try:
        crs = multipoints.crs
    except AttributeError:
        crs = None

    point_df = multipoints.explode(index_parts=False).to_frame("geometry")

    if to_next:
        shift = -1
        filt = lambda x: ~x.index.get_level_values(0).duplicated(keep="first")
    else:
        shift = 1
        filt = lambda x: ~x.index.get_level_values(0).duplicated(keep="last")

    point_df["next"] = point_df.groupby(level=0)["geometry"].shift(shift)

    if cycle:
        first_points = point_df.loc[filt, "geometry"]
        is_last_point = point_df["next"].isna()

        point_df.loc[is_last_point, "next"] = first_points
        assert point_df["next"].notna().all()
    else:
        point_df = point_df[point_df["next"].notna()]

    point_df["geometry"] = [
        LineString([x1, x2]) for x1, x2 in zip(point_df["geometry"], point_df["next"])
    ]
    if isinstance(multipoints.index, pd.MultiIndex):
        point_df.index = point_df.index.droplevel(0)

    if isinstance(multipoints, GeoDataFrame):
        return GeoDataFrame(
            point_df.drop(columns=["next"]), geometry="geometry", crs=crs
        )
    return GeoSeries(point_df["geometry"], crs=crs)


def get_line_segments(lines, extract_unique: bool = False, cycle=False) -> GeoDataFrame:
    try:
        assert lines.index.is_unique
    except AttributeError:
        pass

    lines = to_geoseries(lines)

    if extract_unique:
        points = extract_unique_points(lines.values)
    else:
        coords, indices = shapely.get_coordinates(lines, return_index=True)
        points = GeoSeries(shapely.points(coords), index=indices)

    return multipoints_to_line_segments(points, cycle=cycle)
