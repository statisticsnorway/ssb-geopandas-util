"""Functions that buffer, dissolve and/or explodes geometries while fixing geometries.

The functions do the same as the geopandas buffer, dissolve and explode methods, except
for the following:

- Geometries are made valid after buffer and dissolve.

- The buffer resolution defaults to 50 (geopandas' default is 16).

- If 'by' is not specified, the index will be labeled 0, 1, …, n - 1 after exploded, instead of 0, 0, …, 0 as it will with the geopandas defaults.

- index_parts is set to False, which will be the default in a future version of geopandas.

- The buff function returns a GeoDataFrame, the geopandas method returns a GeoSeries.
"""

from collections.abc import Callable
from collections.abc import Sequence

import numpy as np
import pandas as pd
from geopandas import GeoDataFrame
from geopandas import GeoSeries

from .general import _merge_geometries
from .general import _parallel_unary_union
from .geometry_types import make_all_singlepart
from .polygon_operations import get_cluster_mapper
from .polygon_operations import get_grouped_centroids


def _decide_ignore_index(kwargs: dict) -> tuple[dict, bool]:
    if "ignore_index" in kwargs:
        ignore_index = kwargs.pop("ignore_index")
        return kwargs, ignore_index

    if kwargs.get("by", None) is None:
        return kwargs, True

    if kwargs.get("as_index", True):
        return kwargs, False

    return kwargs, True


def buffdissexp(
    gdf: GeoDataFrame,
    distance: int | float,
    *,
    resolution: int = 50,
    index_parts: bool = False,
    copy: bool = True,
    grid_size: float | int | None = None,
    n_jobs: int = 1,
    join_style: int | str = "round",
    **dissolve_kwargs,
) -> GeoDataFrame:
    """Buffers and dissolves overlapping geometries.

    It takes a GeoDataFrame and buffer, fixes, dissolves, fixes and explodes geometries.
    If the 'by' parameter is not specified, the index will labeled 0, 1, …, n - 1,
    instead of 0, 0, …, 0. If 'by' is speficied, this will be the index.

    Args:
        gdf: the GeoDataFrame that will be buffered, dissolved and exploded.
        distance: the distance (meters, degrees, depending on the crs) to buffer
            the geometry by
        resolution: The number of segments used to approximate a quarter circle.
            Here defaults to 50, as opposed to the default 16 in geopandas.
        index_parts: If False (default), the index after dissolve is respected. If
            True, an integer index level is added during explode.
        copy: Whether to copy the GeoDataFrame before buffering. Defaults to True.
        grid_size: Rounding of the coordinates. Defaults to None.
        n_jobs: Number of threads to use. Defaults to 1.
        join_style: Buffer join style.
        **dissolve_kwargs: additional keyword arguments passed to geopandas' dissolve.

    Returns:
        A buffered GeoDataFrame where overlapping geometries are dissolved.
    """
    dissolve_kwargs, ignore_index = _decide_ignore_index(dissolve_kwargs)

    dissolved = buffdiss(
        gdf,
        distance,
        resolution=resolution,
        copy=copy,
        grid_size=grid_size,
        n_jobs=n_jobs,
        join_style=join_style,
        **dissolve_kwargs,
    )

    return make_all_singlepart(
        dissolved, ignore_index=ignore_index, index_parts=index_parts
    )


def buffdiss(
    gdf: GeoDataFrame,
    distance: int | float,
    resolution: int = 50,
    copy: bool = True,
    n_jobs: int = 1,
    join_style: int | str = "round",
    **dissolve_kwargs,
) -> GeoDataFrame:
    """Buffers and dissolves geometries.

    It takes a GeoDataFrame and buffer, fixes, dissolves and fixes geometries.
    If the 'by' parameter is not specified, the index will labeled 0, 1, …, n - 1,
    instead of 0, 0, …, 0. If 'by' is speficied, this will be the index.

    Args:
        gdf: the GeoDataFrame that will be
            buffered and dissolved.
        distance: the distance (meters, degrees, depending on the crs) to buffer
            the geometry by
        resolution: The number of segments used to approximate a quarter circle.
            Here defaults to 50, as opposed to the default 16 in geopandas.
        join_style: Buffer join style.
        copy: Whether to copy the GeoDataFrame before buffering. Defaults to True.
        n_jobs: Number of threads to use. Defaults to 1.
        **dissolve_kwargs: additional keyword arguments passed to geopandas' dissolve.

    Returns:
        A buffered GeoDataFrame where geometries are dissolved.

    Examples:
    --------
    Create some random points.

    >>> import sgis as sg
    >>> import numpy as np
    >>> points = sg.read_parquet_url(
    ...     "https://media.githubusercontent.com/media/statisticsnorway/ssb-sgis/main/tests/testdata/points_oslo.parquet"
    ... )[["geometry"]]
    >>> points["group"] = np.random.choice([*"abd"], len(points))
    >>> points["number"] = np.random.random(size=len(points))
    >>> points
                               geometry group    number
    0    POINT (263122.700 6651184.900)     a  0.878158
    1    POINT (272456.100 6653369.500)     a  0.693311
    2    POINT (270082.300 6653032.700)     b  0.323960
    3    POINT (259804.800 6650339.700)     a  0.606745
    4    POINT (272876.200 6652889.100)     a  0.194360
    ..                              ...   ...       ...
    995  POINT (266801.700 6647844.500)     a  0.814424
    996  POINT (261274.000 6653593.400)     b  0.769479
    997  POINT (263542.900 6645427.000)     a  0.925991
    998  POINT (269226.700 6650628.000)     b  0.431972
    999  POINT (264570.300 6644239.500)     d  0.555239

    Buffer by 100 meters and dissolve.

    >>> sg.buffdiss(points, 100)
                                                geometry group    number
    0  MULTIPOLYGON (((256421.833 6649878.117, 256420...     d  0.580157

    Dissolve by 'group' and get sum of columns.

    >>> sg.buffdiss(points, 100, by="group", aggfunc="sum")
                                                    geometry      number
    group
    a      MULTIPOLYGON (((258866.258 6648220.031, 258865...  167.265619
    b      MULTIPOLYGON (((258404.858 6647830.931, 258404...  171.939169
    d      MULTIPOLYGON (((258180.258 6647935.731, 258179...  156.964300

    To get the 'by' columns as columns, not index.

    >>> sg.buffdiss(points, 100, by="group", as_index=False)
      group                                           geometry    number
    0     a  MULTIPOLYGON (((258866.258 6648220.031, 258865...  0.323948
    1     b  MULTIPOLYGON (((258404.858 6647830.931, 258404...  0.687635
    2     d  MULTIPOLYGON (((258180.258 6647935.731, 258179...  0.580157
    """
    buffered = buff(
        gdf, distance, resolution=resolution, copy=copy, join_style=join_style
    )

    return _dissolve(buffered, n_jobs=n_jobs, **dissolve_kwargs)


def _dissolve(
    gdf: GeoDataFrame,
    aggfunc: str = "first",
    grid_size: None | float = None,
    n_jobs: int = 1,
    **dissolve_kwargs,
) -> GeoDataFrame:

    if not len(gdf):
        return gdf

    geom_col = gdf._geometry_column_name

    by = dissolve_kwargs.pop("by", None)

    by_was_none = not bool(by)

    if by is None and dissolve_kwargs.get("level") is None:
        by = np.zeros(len(gdf), dtype="int64")
        other_cols = list(gdf.columns.difference({geom_col}))
    else:
        if isinstance(by, str):
            by = [by]
        other_cols = list(gdf.columns.difference({geom_col} | set(by or {})))

    try:
        is_one_hit = gdf.groupby(by, **dissolve_kwargs).transform("size") == 1
    except IndexError:
        # if no rows when dropna=True
        original_by = [x for x in by]
        query = gdf[by.pop(0)].notna()
        for col in gdf[by]:
            query &= gdf[col].notna()
        gdf = gdf.loc[query]
        assert not len(gdf), gdf
        if not by_was_none and dissolve_kwargs.get("as_index", True):
            try:
                gdf = gdf.set_index(original_by)
            except Exception as e:
                print(gdf)
                print(original_by)
                raise e
        return gdf

    if not by_was_none and dissolve_kwargs.get("as_index", True):
        one_hit = gdf[is_one_hit].set_index(by)
    else:
        one_hit = gdf[is_one_hit]
    many_hits = gdf[~is_one_hit]

    if not len(many_hits):
        return GeoDataFrame(one_hit, geometry=geom_col, crs=gdf.crs)

    dissolved = many_hits.groupby(by, **dissolve_kwargs)[other_cols].agg(aggfunc)

    # dissolved = gdf.groupby(by, **dissolve_kwargs)[other_cols].agg(aggfunc)

    if n_jobs > 1:
        try:
            agged = _parallel_unary_union(
                many_hits, n_jobs=n_jobs, by=by, grid_size=grid_size, **dissolve_kwargs
            )
            dissolved[geom_col] = agged
            return GeoDataFrame(dissolved, geometry=geom_col, crs=gdf.crs)
        except Exception as e:
            print(e, dissolved, agged, many_hits)
            raise e

    geoms_agged = many_hits.groupby(by, **dissolve_kwargs)[geom_col].agg(
        lambda x: _merge_geometries(x, grid_size=grid_size)
    )

    if not dissolve_kwargs.get("as_index"):
        try:
            geoms_agged = geoms_agged[geom_col]
        except KeyError:
            pass

    dissolved[geom_col] = geoms_agged

    return GeoDataFrame(
        pd.concat([dissolved, one_hit]).sort_index(), geometry=geom_col, crs=gdf.crs
    )


def diss(
    gdf: GeoDataFrame,
    by: str | Sequence[str] | None = None,
    aggfunc: str | Callable | dict[str, str | Callable] = "first",
    as_index: bool = True,
    grid_size: float | int | None = None,
    n_jobs: int = 1,
    **dissolve_kwargs,
) -> GeoDataFrame:
    """Dissolves geometries.

    It takes a GeoDataFrame and dissolves and fixes geometries.

    Args:
        gdf: the GeoDataFrame that will be dissolved and exploded.
        by: Columns to dissolve by.
        aggfunc: How to aggregate the non-geometry colums not in "by".
        as_index: Whether the 'by' columns should be returned as index. Defaults to
            True to be consistent with geopandas.
        grid_size: Rounding of the coordinates. Defaults to None.
        n_jobs: Number of threads to use. Defaults to 1.
        **dissolve_kwargs: additional keyword arguments passed to geopandas' dissolve.

    Returns:
        A GeoDataFrame with dissolved geometries.
    """
    if not len(gdf):
        if as_index:
            try:
                return gdf.set_index(by)
            except Exception:
                return gdf
        else:
            return gdf

    return _dissolve(
        gdf,
        by=by,
        aggfunc=aggfunc,
        grid_size=grid_size,
        n_jobs=n_jobs,
        as_index=as_index,
        **dissolve_kwargs,
    )


def dissexp(
    gdf: GeoDataFrame,
    by: str | Sequence[str] | None = None,
    aggfunc: str | Callable | dict[str, str | Callable] = "first",
    as_index: bool = True,
    index_parts: bool = False,
    grid_size: float | int | None = None,
    n_jobs: int = 1,
    **dissolve_kwargs,
) -> GeoDataFrame:
    """Dissolves overlapping geometries.

    It takes a GeoDataFrame and dissolves, fixes and explodes geometries.

    Args:
        gdf: the GeoDataFrame that will be dissolved and exploded.
        by: Columns to dissolve by.
        aggfunc: How to aggregate the non-geometry colums not in "by".
        as_index: Whether the 'by' columns should be returned as index. Defaults to
            True to be consistent with geopandas.
        index_parts: If False (default), the index after dissolve is respected. If
            True, an integer index level is added during explode.
        grid_size: Rounding of the coordinates. Defaults to None.
        n_jobs: Number of threads to use. Defaults to 1.
        **dissolve_kwargs: additional keyword arguments passed to geopandas' dissolve.

    Returns:
        A GeoDataFrame where overlapping geometries are dissolved.
    """
    dissolve_kwargs = dissolve_kwargs | {
        "by": by,
        "as_index": as_index,
    }

    dissolve_kwargs, ignore_index = _decide_ignore_index(dissolve_kwargs)

    dissolved = diss(
        gdf, aggfunc=aggfunc, grid_size=grid_size, n_jobs=n_jobs, **dissolve_kwargs
    )

    return make_all_singlepart(
        dissolved, ignore_index=ignore_index, index_parts=index_parts
    )


def dissexp_by_cluster(
    gdf: GeoDataFrame, predicate: str | None = None, n_jobs: int = 1, **dissolve_kwargs
) -> GeoDataFrame:
    """Dissolves overlapping geometries through clustering with sjoin and networkx.

    Works exactly like dissexp, but, before dissolving, the geometries are divided
    into clusters based on overlap (uses the function sgis.get_polygon_clusters).
    The geometries are then dissolved based on this column (and optionally other
    columns).

    This might be many times faster than a regular dissexp, if there are many
    non-overlapping geometries.

    Args:
        gdf: the GeoDataFrame that will be dissolved and exploded.
        predicate: Spatial predicate to use.
        n_jobs: Number of threads to use. Defaults to 1.
        **dissolve_kwargs: Keyword arguments passed to geopandas' dissolve.

    Returns:
        A GeoDataFrame where overlapping geometries are dissolved.
    """
    return _run_func_by_cluster(
        dissexp, gdf, predicate=predicate, n_jobs=n_jobs, **dissolve_kwargs
    )


def diss_by_cluster(
    gdf: GeoDataFrame, predicate=None, n_jobs: int = 1, **dissolve_kwargs
) -> GeoDataFrame:
    """Dissolves overlapping geometries through clustering with sjoin and networkx.

    Works exactly like dissexp, but, before dissolving, the geometries are divided
    into clusters based on overlap (uses the function sgis.get_polygon_clusters).
    The geometries are then dissolved based on this column (and optionally other
    columns).

    This might be many times faster than a regular dissexp, if there are many
    non-overlapping geometries.

    Args:
        gdf: the GeoDataFrame that will be dissolved and exploded.
        predicate: Spatial predicate to use.
        n_jobs: Number of threads to use. Defaults to 1.
        **dissolve_kwargs: Keyword arguments passed to geopandas' dissolve.

    Returns:
        A GeoDataFrame where overlapping geometries are dissolved.
    """
    return _run_func_by_cluster(
        diss, gdf, predicate=predicate, n_jobs=n_jobs, **dissolve_kwargs
    )


def _run_func_by_cluster(
    func: Callable,
    gdf: GeoDataFrame,
    predicate: str | None = None,
    n_jobs: int = 1,
    **dissolve_kwargs,
) -> GeoDataFrame:
    is_geoseries = isinstance(gdf, GeoSeries)

    by = dissolve_kwargs.pop("by", [])
    if isinstance(by, str):
        by = [by]
    elif by:
        by = list(by)

    if not len(gdf):
        return func(gdf, by=by, **dissolve_kwargs)

    def get_group_clusters(group: GeoDataFrame):
        """Adds cluster column. Applied to each group because much faster."""
        group = group.reset_index(drop=True)
        group["_cluster"] = get_cluster_mapper(
            group, predicate=predicate
        )  # component_mapper
        group["_cluster"] = get_grouped_centroids(group, groupby="_cluster")
        return group

    if by:
        dissolved = (
            make_all_singlepart(gdf)
            .groupby(by, group_keys=True, dropna=False, as_index=False)
            .apply(get_group_clusters)
            .pipe(func, by=["_cluster"] + by, n_jobs=n_jobs, **dissolve_kwargs)
        )
    else:
        dissolved = get_group_clusters(make_all_singlepart(gdf)).pipe(
            func, by="_cluster", n_jobs=n_jobs, **dissolve_kwargs
        )

    if not by:
        dissolved = dissolved.reset_index(drop=True)

    elif dissolve_kwargs.get("as_index", True):
        dissolved.index = dissolved.index.droplevel(0)

    if is_geoseries:
        return dissolved.geometry

    return dissolved.drop("_cluster", axis=1, errors="ignore")


def buffdissexp_by_cluster(
    gdf: GeoDataFrame,
    distance: int | float,
    *,
    resolution: int = 50,
    copy: bool = True,
    n_jobs: int = 1,
    join_style: int | str = "round",
    **dissolve_kwargs,
) -> GeoDataFrame:
    """Buffers and dissolves overlapping geometries.

    Works exactly like buffdissexp, but, before dissolving, the geometries are divided
    into clusters based on overlap (uses the function sgis.get_polygon_clusters).
    The geometries are then dissolved based on this column (and optionally other
    columns).

    This might be many times faster than a regular buffdissexp, if there are many
    non-overlapping geometries.

    Args:
        gdf: the GeoDataFrame that will be buffered, dissolved and exploded.
        distance: the distance (meters, degrees, depending on the crs) to buffer
            the geometry by
        resolution: The number of segments used to approximate a quarter circle.
            Here defaults to 50, as opposed to the default 16 in geopandas.
        join_style: Buffer join style.
        copy: Whether to copy the GeoDataFrame before buffering. Defaults to True.
        n_jobs: int = 1,
        **dissolve_kwargs: additional keyword arguments passed to geopandas' dissolve.

    Returns:
        A buffered GeoDataFrame where overlapping geometries are dissolved.
    """
    buffered = buff(
        gdf,
        distance,
        resolution=resolution,
        copy=copy,
        join_style=join_style,
    )
    return dissexp_by_cluster(buffered, n_jobs=n_jobs, **dissolve_kwargs)


def buff(
    gdf: GeoDataFrame | GeoSeries,
    distance: int | float,
    resolution: int = 50,
    copy: bool = True,
    join_style: int | str = "round",
    **buffer_kwargs,
) -> GeoDataFrame:
    """Buffers a GeoDataFrame with high resolution and returns a new GeoDataFrame.

    Args:
        gdf: the GeoDataFrame that will be buffered, dissolved and exploded.
        distance: the distance (meters, degrees, depending on the crs) to buffer
            the geometry by
        resolution: The number of segments used to approximate a quarter circle.
            Here defaults to 50, as opposed to the default 16 in geopandas.
        join_style: Buffer join style.
        copy: Whether to copy the GeoDataFrame before buffering. Defaults to True.
        **buffer_kwargs: additional keyword arguments passed to geopandas' buffer.

    Returns:
        A buffered GeoDataFrame.
    """
    if isinstance(gdf, GeoSeries):
        return gdf.buffer(
            distance, resolution=resolution, join_style=join_style, **buffer_kwargs
        ).make_valid()

    if copy:
        gdf = gdf.copy()

    gdf[gdf._geometry_column_name] = gdf.buffer(
        distance, resolution=resolution, join_style=join_style, **buffer_kwargs
    ).make_valid()

    return gdf
