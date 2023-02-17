import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
from geopandas import GeoDataFrame, GeoSeries
from shapely import (
    Geometry,
    area,
    get_exterior_ring,
    get_interior_ring,
    get_num_interior_rings,
    get_parts,
    polygons,
)
from shapely.ops import unary_union

from .buffer_dissolve_explode import buff


def clean_geoms(
    gdf: GeoDataFrame | GeoSeries,
    ignore_index=False,
    single_geom_type: bool = True,
) -> GeoDataFrame | GeoSeries:
    """
    Repairs geometries, removes geometries that are invalid, empty, NaN and None,
    keeps only rows with in the data.

    Args:
        gdf: GeoDataFrame or GeoSeries to be fixed or removed.
        ignore_index: whether the index should be reset and dropped. Defaults to False
          to be consistent with pandas.
        single_geomtype: if only the most common geometry type
          ((multi)point, (multi)line, (multi)poly) should be kept. Defaults to False,
          even though this might raise an exception in overlay operations
          Please note that in order for the function to not do anything unexpected.

    Returns:
        GeoDataFrame or GeoSeries with fixed geometries and only the rows with valid,
        non-empty and not-NaN/-None geometries.

    """

    if not isinstance(gdf, (GeoDataFrame, GeoSeries)):
        raise TypeError(f"'gdf' should be GeoDataFrame or GeoSeries, got {type(gdf)}")

    fixed = gdf.make_valid()

    cleaned = fixed.loc[(fixed.is_valid) & (~fixed.is_empty) & (fixed.notna())]

    if single_geom_type:
        cleaned = to_single_geom_type(cleaned)

    if isinstance(gdf, GeoDataFrame):
        gdf = gdf.loc[cleaned.index]
        gdf[gdf._geometry_column_name] = cleaned
    else:
        gdf = cleaned

    if ignore_index:
        gdf = gdf.reset_index(drop=True)

    return gdf


def to_single_geom_type(
    gdf: GeoDataFrame | GeoSeries, ignore_index: bool = False
) -> GeoDataFrame | GeoSeries:
    """
    overlay godtar ikke blandede geometrityper i samme gdf.
    """

    polys = ["Polygon", "MultiPolygon"]
    lines = ["LineString", "MultiLineString", "LinearRing"]
    points = ["Point", "MultiPoint"]

    poly_check = len(gdf.loc[gdf.geom_type.isin(polys)])
    lines_check = len(gdf.loc[gdf.geom_type.isin(lines)])
    points_check = len(gdf.loc[gdf.geom_type.isin(points)])

    _max = max([poly_check, lines_check, points_check])

    if _max == len(gdf):
        return gdf

    if poly_check == _max:
        gdf = gdf.loc[gdf.geom_type.isin(polys)]
    elif lines_check == _max:
        gdf = gdf.loc[gdf.geom_type.isin(lines)]
    elif points_check == _max:
        gdf = gdf.loc[gdf.geom_type.isin(points)]
    else:
        raise ValueError(
            "Mixed geometry types and equal amount of two or all the types."
        )

    if ignore_index:
        gdf = gdf.reset_index(drop=True)

    return gdf


def close_holes(
    geom: GeoDataFrame | GeoSeries | Geometry,
    max_km2: int | None = None,
    copy: bool = True,
) -> GeoDataFrame | GeoSeries | Geometry:
    """
    Closes holes in polygons. The operation is done row-wise if 'geom' is a GeoDataFrame
    or GeoSeries.

    max_km2: if None (default), all holes are closed.
      Otherwise, closes holes with an area below the specified number in square
      kilometers.
    """

    if copy:
        geom = geom.copy()

    if isinstance(geom, GeoDataFrame):
        geom["geometry"] = geom.geometry.map(lambda x: _close_holes_geom(x, max_km2))

    elif isinstance(geom, gpd.GeoSeries):
        geom = geom.map(lambda x: _close_holes_geom(x, max_km2))
        geom = gpd.GeoSeries(geom)

    else:
        geom = _close_holes_geom(geom, max_km2)

    return geom


def _close_holes_geom(geom, max_km2=None):
    """closes holes within one shapely geometry."""

    # dissolve the exterior ring(s)
    if max_km2 is None:
        holes_closed = polygons(get_exterior_ring(get_parts(geom)))
        return unary_union(holes_closed)

    # start with list containing the geometry,
    # then append all holes smaller than 'max_km2'.
    holes_closed = [geom]
    singlepart = get_parts(geom)
    for part in singlepart:
        antall_indre_ringer = get_num_interior_rings(part)
        if antall_indre_ringer > 0:
            for n in range(antall_indre_ringer):
                hull = polygons(get_interior_ring(part, n))
                if area(hull) / 1_000_000 < max_km2:
                    holes_closed.append(hull)
    return unary_union(holes_closed)


def gdf_concat(
    gdfs: list[GeoDataFrame],
    crs: str | int | None = None,
    ignore_index: bool = True,
    geometry: str = "geometry",
    **kwargs,
) -> GeoDataFrame:
    """
    Concats geodataframes rowwise.
    Ignores index, changes to common crs.
    If no crs is given, chooses the first crs in the list of geodataframes.

    """

    gdfs = [gdf for gdf in gdfs if len(gdf)]

    if not len(gdfs):
        raise ValueError("gdf_concat: alle gdf-ene har 0 rader")

    if not crs:
        crs = gdfs[0].crs

    try:
        gdfs = [gdf.to_crs(crs) for gdf in gdfs]
    except ValueError:
        print(
            "OBS: ikke alle gdf-ene dine har crs. Hvis du nå samler latlon og utm, "
            "må du først bestemme crs med set_crs(), så gi dem samme crs med to_crs()"
        )

    return GeoDataFrame(
        pd.concat(gdfs, ignore_index=ignore_index, **kwargs), geometry=geometry, crs=crs
    )


def to_gdf(geom: GeoSeries | Geometry | str, crs=None, **kwargs) -> GeoDataFrame:
    """
    Konverterer til geodataframe fra geoseries, shapely-objekt, wkt, liste med
    shapely-objekter eller shapely-sekvenser.
    OBS: når man har shapely-objekter eller wkt, bør man velge crs.
    """

    if not crs:
        if isinstance(geom, str):
            raise ValueError("Du må bestemme crs når input er string.")
        crs = geom.crs

    if isinstance(geom, str):
        from shapely.wkt import loads

        geom = loads(geom)
        gdf = GeoDataFrame({"geometry": gpd.GeoSeries(geom)}, crs=crs, **kwargs)
    else:
        gdf = GeoDataFrame({"geometry": gpd.GeoSeries(geom)}, crs=crs, **kwargs)

    return gdf


def clean_clip(
    gdf: GeoDataFrame | GeoSeries,
    mask: GeoDataFrame | GeoSeries | Geometry,
    keep_geom_type: bool = True,
    **kwargs,
) -> GeoDataFrame | GeoSeries:
    """Clip geometries to the mask extent, then cleans the geometries.
    geopandas.clip does a fast clipping, with no guarantee for valid outputs.
    Here, geometries are made valid, then invalid, empty, nan and None geometries are
    removed.

    """

    if not isinstance(gdf, (GeoDataFrame, GeoSeries)):
        raise TypeError(f"'gdf' should be GeoDataFrame or GeoSeries, got {type(gdf)}")

    return gdf.clip(mask, keep_geom_type=keep_geom_type, **kwargs).pipe(clean_geoms)


def overlay(left_gdf, right_gdf, drop_dupcol=True, **kwargs) -> GeoDataFrame:
    """
    som gpd.overlay bare at kolonner i right_gdf som også er i left_gdf fjernes
    (fordi det snart vil gi feilmelding i geopandas) og kolonner som har med index
    å gjøre fjernes, fordi sjoin returnerer index_right som kolonnenavn,
    som gir feilmelding ved neste join.
    """

    left_gdf = left_gdf.loc[:, ~left_gdf.columns.str.contains("index|level_")]
    right_gdf = right_gdf.loc[:, ~right_gdf.columns.str.contains("index|level_")]

    if drop_dupcol:
        right_gdf = right_gdf.loc[
            :, right_gdf.columns.difference(left_gdf.columns.difference(["geometry"]))
        ]

    try:
        joined = left_gdf.overlay(right_gdf, **kwargs)
    except Exception:
        right_gdf = right_gdf.to_crs(left_gdf.crs)
        left_gdf = clean_geoms(left_gdf, single_geom_type=True)
        right_gdf = clean_geoms(right_gdf, single_geom_type=True)
        joined = left_gdf.overlay(right_gdf, **kwargs)

    right_gdf = clean_geoms(right_gdf, single_geom_type=True)

    return joined.loc[:, ~joined.columns.str.contains("index|level_")]


def sjoin(left_gdf, right_gdf, drop_dupcol=True, **kwargs) -> GeoDataFrame:
    """
    som gpd.sjoin bare at kolonner i right_gdf som også er i left_gdf fjernes
    (fordi det snart vil gi feilmelding i geopandas) og kolonner som har med index
     å gjøre fjernes, fordi sjoin returnerer index_right som kolonnenavn,
     som gir feilmelding ved neste join.
    """

    left_gdf = left_gdf.loc[:, ~left_gdf.columns.str.contains("index|level_")]
    right_gdf = right_gdf.loc[:, ~right_gdf.columns.str.contains("index|level_")]

    if drop_dupcol:
        right_gdf = right_gdf.loc[
            :, right_gdf.columns.difference(left_gdf.columns.difference(["geometry"]))
        ]

    try:
        joined = left_gdf.sjoin(right_gdf, **kwargs)
    except Exception:
        right_gdf = right_gdf.to_crs(left_gdf.crs)
        left_gdf = clean_geoms(left_gdf, single_geom_type=True)
        right_gdf = clean_geoms(right_gdf, single_geom_type=True)
        joined = left_gdf.sjoin(right_gdf, **kwargs)

    return joined.loc[:, ~joined.columns.str.contains("index|level_")]


def overlay_update(gdf1: GeoDataFrame, gdf2: GeoDataFrame, **kwargs) -> GeoDataFrame:
    """En overlay-variant som ikke finnes i geopandas."""

    out = gdf1.overlay(gdf2, how="difference", keep_geom_type=True, **kwargs)
    out = out.loc[:, ~out.columns.str.contains("index|level_")]
    out = gdf_concat([out, gdf2])
    return out


def snap_to(punkter, snap_til, maks_distanse=500, copy=False):
    """
    Snapper (flytter) punkter til naermeste punkt/linje/polygon innen en gitt
    maks_distanse. Går via nearest_points for å finne det nøyaktige punktet. Med kun
    snap() blir det unøyaktig. Funker med geodataframes og geoseries."""

    from shapely.ops import nearest_points, snap

    snap_til_shapely = snap_til.unary_union

    if copy:
        punkter = punkter.copy()

    if isinstance(punkter, GeoDataFrame):
        for i, punkt in enumerate(punkter.geometry):
            nearest = nearest_points(punkt, snap_til_shapely)[1]
            snappet_punkt = snap(punkt, nearest, tolerance=maks_distanse)
            punkter.geometry.iloc[i] = snappet_punkt

    if isinstance(punkter, gpd.GeoSeries):
        for i, punkt in enumerate(punkter):
            nearest = nearest_points(punkt, snap_til_shapely)[1]
            snappet_punkt = snap(punkt, nearest, tolerance=maks_distanse)
            punkter.iloc[i] = snappet_punkt

    return punkter


def to_multipoint(geom, copy=False):
    from shapely import force_2d
    from shapely.wkt import loads

    if copy:
        geom = geom.copy()

    def til_multipunkt_i_shapely(geom):
        koordinater = "".join(
            [x for x in geom.wkt if x.isdigit() or x.isspace() or x == "." or x == ","]
        ).strip()

        alle_punkter = [
            loads(f"POINT ({punkt.strip()})") for punkt in koordinater.split(",")
        ]

        return unary_union(alle_punkter)

    if isinstance(geom, GeoDataFrame):
        geom["geometry"] = force_2d(geom.geometry)
        geom["geometry"] = geom.geometry.apply(lambda x: til_multipunkt_i_shapely(x))

    elif isinstance(geom, gpd.GeoSeries):
        geom = force_2d(geom)
        geom = geom.apply(lambda x: til_multipunkt_i_shapely(x))

    else:
        geom = force_2d(geom)
        geom = til_multipunkt_i_shapely(unary_union(geom))

    return geom


def find_neighbours(
    gdf: GeoDataFrame | GeoSeries,
    possible_neighbours: GeoDataFrame | GeoSeries,
    id_col: str,
    within_distance: int = 1,
):
    """Return geometries that are less than 1 meter
    finner geometrier som er maks. 1 meter unna.
    i alle retninger (queen contiguity).

    Args:
        gdf: the geometry
    """

    if gdf.crs == 4326 and within_distance > 0.01:
        warnings.warn(
            "'gdf' has latlon crs, meaning the 'within_distance' paramter "
            "will not be in meters, but degrees."
        )

    possible_neighbours = possible_neighbours.to_crs(gdf.crs)

    joined = (
        gdf.buffer(within_distance).to_frame().sjoin(possible_neighbours, how="inner")
    )

    return [x for x in joined[id_col].unique()]


def find_neighbors(
    gdf: GeoDataFrame | GeoSeries,
    possible_neighbors: GeoDataFrame | GeoSeries,
    id_col: str,
    within_distance: int = 1,
):
    return find_neighbours(gdf, possible_neighbors, id_col, within_distance)


def try_overlay(
    gdf1: GeoDataFrame,
    gdf2: GeoDataFrame,
    presicion_col: bool = True,
    max_rounding: int = 3,
    single_geomtype: bool = True,
    **kwargs,
) -> GeoDataFrame:
    """
    Overlay, i hvert fall union, har gitt TopologyException: found non-noded
    intersection error from overlay. https://github.com/geopandas/geopandas/issues/1724
    En løsning er å avrunde koordinatene for å få valid polygon. Prøver først uten
    avrunding, så runder av til 10 koordinatdesimaler, så 9, 8, ..., og så gir opp på 0

    Args:
      presisjonskolonne: om man skal inkludere en kolonne som angir hvilken avrunding
        som måtte til.
      max_avrunding: hvilken avrunding man stopper på. 0 betyr at man fortsetter fram
        til 0 desimaler.
    """

    try:
        gdf1 = clean_geoms(gdf1, single_geomtype=single_geomtype)
        gdf2 = clean_geoms(gdf2, single_geomtype=single_geomtype)
        return gdf1.overlay(gdf2, **kwargs)

    except Exception:
        from shapely.wkt import dumps, loads

        # loop through list from 10 to 'max_rounding'

        roundings = list(range(max_rounding, 11))
        roundings.reverse()

        for rounding in roundings:
            try:
                gdf1.geometry = [
                    loads(dumps(gdf, rounding_precision=rounding))
                    for geom in gdf1.geometry
                ]
                gdf2.geometry = [
                    loads(dumps(gdf, rounding_precision=rounding))
                    for geom in gdf2.geometry
                ]

                gdf1 = clean_geoms(gdf1, single_geomtype=single_geomtype)
                gdf2 = clean_geoms(gdf2, single_geomtype=single_geomtype)

                overlayet = gdf1.overlay(gdf2, **kwargs)

                if presicion_col:
                    overlayet["avrunding"] = rounding

                return overlayet

            except Exception:
                rounding -= 1

        # returnerer feilmeldingen hvis det fortsatt ikke funker
        gdf1.overlay(gdf2, **kwargs)


def try_diss(gdf, presicion_col=True, max_rounding=5, **kwargs):
    """
    dissolve har gitt TopologyException: found non-noded intersection error from
    overlay. En løsning er å avrunde koordinatene for å få valid polygon.
    Prøver først uten avrunding, så runder av til 10 koordinatdesimaler, så 9, 8, ...,
    og så gir opp på 0

    Args:
      presisjonskolonne: om man skal inkludere en kolonne som angir hvilken avrunding
        som måtte til.
      max_avrunding: hvilken avrunding man stopper på. 0 betyr at man fortsetter fram
        til 0 desimaler.
    """

    from .buffer_dissolve_explode import diss

    try:
        dissolvet = diss(gdf, **kwargs)
        if presicion_col:
            dissolvet["avrunding"] = np.nan
        return dissolvet

    except Exception:
        from shapely.wkt import dumps, loads

        # liste fra 10 til 0, eller max_avrunding til 0
        avrundinger = list(range(max_rounding, 11))
        avrundinger.reverse()

        for avrunding in avrundinger:
            try:
                gdf.geometry = [
                    loads(dumps(gdf, rounding_precision=avrunding))
                    for geom in gdf.geometry
                ]

                dissolvet = diss(gdf, **kwargs)

                if presicion_col:
                    dissolvet["avrunding"] = avrunding

                return dissolvet

            except Exception:
                avrunding -= 1

        # returnerer feilmeldingen hvis det fortsatt ikke funker
        diss(gdf, **kwargs)


def gridish(gdf, meter, x2=False, minmax=False):
    """
    Enkel rutedeling av dataene, for å kunne loope tunge greier for områder i valgfri
    størrelse. Gir dataene kolonne med avrundede minimum-xy-koordinater, altså det
    sørvestlige hjørnets koordinater avrundet.

    minmax=True gir kolonnen 'gridish_max', som er avrundede maksimum-koordinater,
    altså koordinatene i det nordøstlige hjørtet.
    Hvis man skal gjøre en overlay/sjoin og dataene er større i utstrekning enn
    områdene man vil loope for.

    x2=True gir kolonnen 'gridish2', med ruter 1/2 hakk nedover og bortover.
    Hvis grensetilfeller er viktig, kan man måtte loope for begge gridish-kolonnene.

    """

    # rund ned koordinatene og sett sammen til kolonne
    gdf["gridish"] = [
        f"{round(minx/meter)}_{round(miny/meter)}"
        for minx, miny in zip(gdf.geometry.bounds.minx, gdf.geometry.bounds.miny)
    ]

    if minmax:
        gdf["gridish_max"] = [
            f"{round(maxx/meter)}_{round(maxy/meter)}"
            for maxx, maxy in zip(gdf.geometry.bounds.maxx, gdf.geometry.bounds.maxy)
        ]

    if x2:
        gdf["gridish_x"] = gdf.geometry.bounds.minx / meter

        unike_x = gdf["gridish_x"].astype(int).unique()
        unike_x.sort()

        for x in unike_x:
            gdf.loc[
                (gdf["gridish_x"] >= x - 0.5) & (gdf["gridish_x"] < x + 0.5),
                "gridish_x2",
            ] = (
                x + 0.5
            )

        # samme for y
        gdf["gridish_y"] = gdf.geometry.bounds.miny / meter
        unike_y = gdf["gridish_y"].astype(int).unique()
        unike_y.sort()
        for y in unike_y:
            gdf.loc[
                (gdf["gridish_y"] >= y - 0.5) & (gdf["gridish_y"] < y + 0.5),
                "gridish_y2",
            ] = (
                y + 0.5
            )

        gdf["gridish2"] = (
            gdf["gridish_x2"].astype(str) + "_" + gdf["gridish_y2"].astype(str)
        )

        gdf = gdf.drop(["gridish_x", "gridish_y", "gridish_x2", "gridish_y2"], axis=1)

    return gdf


def random_points(n: int, mask=None) -> GeoDataFrame:
    """lager n tilfeldige punkter innenfor et gitt område (mask)."""
    import random

    from shapely.wkt import loads

    if mask is None:
        x = np.array([random.random() * 10**7 for _ in range(n * 1000)])
        y = np.array([random.random() * 10**8 for _ in range(n * 1000)])
        punkter = to_gdf([loads(f"POINT ({x} {y})") for x, y in zip(x, y)], crs=25833)
        return punkter
    mask_kopi = mask.copy()
    mask_kopi = mask_kopi.to_crs(25833)
    out = GeoDataFrame({"geometry": []}, geometry="geometry", crs=25833)
    while len(out) < n:
        x = np.array([random.random() * 10**7 for _ in range(n * 1000)])
        x = x[(x > mask_kopi.bounds.minx.iloc[0]) & (x < mask_kopi.bounds.maxx.iloc[0])]

        y = np.array([random.random() * 10**8 for _ in range(n * 1000)])
        y = y[(y > mask_kopi.bounds.miny.iloc[0]) & (y < mask_kopi.bounds.maxy.iloc[0])]

        punkter = til_gdf([loads(f"POINT ({x} {y})") for x, y in zip(x, y)], crs=25833)
        overlapper = punkter.clip(mask_kopi)
        out = gdf_concat([out, overlapper])
    out = out.sample(n).reset_index(drop=True).to_crs(mask.crs)
    out["idx"] = out.index
    return out


def count_within_distance(
    gdf1: GeoDataFrame, gdf2: GeoDataFrame, distance=0, col_name="n"
) -> GeoDataFrame:
    """
    Teller opp antall nærliggende eller overlappende (hvis avstan=0) geometrier i
    to geodataframes. gdf1 returneres med en ny kolonne ('antall') som forteller hvor
    mange geometrier (rader) fra gdf2 som er innen spesifisert distance .
    """

    gdf1["temp_idx"] = range(len(gdf1))
    gdf2["temp_idx2"] = range(len(gdf2))

    if distance > 0:
        gdf2 = buff(gdf2[["geometry"]], distance)

    joined = (
        gdf1[["temp_idx", "geometry"]]
        .sjoin(gdf2[["geometry"]], how="inner")["temp_idx"]
        .value_counts()
    )

    gdf1[col_name] = gdf1["temp_idx"].map(joined).fillna(0)

    return gdf1.drop("temp_idx", axis=1)
