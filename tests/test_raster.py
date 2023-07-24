# %%
import sys
from pathlib import Path

import numpy as np
import skimage
import xarray as xr
from IPython.display import display
from shapely import box


src = str(Path(__file__).parent.parent) + "/src"
testdata = str(Path(__file__).parent.parent) + "/tests/testdata/raster"

sys.path.insert(0, src)

import sgis as sg


path_singleband = testdata + "/dtm_10.tif"
path_two_bands = testdata + "/dtm_10_two_bands.tif"


def test_sample():
    r = sg.Raster.from_path(path_two_bands)
    sample = r.sample(10)
    sample2 = r.sample(10)
    sg.explore(r.load().to_gdf(), sample.to_gdf(), sample2.to_gdf())


def test_transform():
    gdf = sg.random_points(10)
    transform1 = sg.Raster.get_transform_from_bounds(gdf, shape=(1, 1))

    # should also work with geoseries, shapely geometry and tuple
    transform = sg.Raster.get_transform_from_bounds(gdf.geometry, shape=(1, 1))
    assert transform1 == transform
    transform = sg.Raster.get_transform_from_bounds(gdf.unary_union, shape=(1, 1))
    assert transform1 == transform
    transform = sg.Raster.get_transform_from_bounds(gdf.total_bounds, shape=(1, 1))
    assert transform1 == transform
    transform = sg.Raster.get_transform_from_bounds(
        tuple(gdf.total_bounds), shape=(1, 1)
    )
    assert transform1 == transform


def test_elevation():
    arr = np.array(
        [
            [100, 100, 100, 100, 100],
            [100, 110, 110, 110, 100],
            [100, 110, 120, 110, 100],
            [100, 110, 110, 110, 100],
            [100, 100, 100, 100, 100],
        ]
    )
    print(arr)

    # creating a simple Raster with a resolution of 10 (50 / width or height).
    r = sg.ElevationRaster.from_array(arr, crs=None, bounds=(0, 0, 50, 50))
    print(r.res)
    gradient = r.gradient(copy=True)
    print(gradient.array)
    assert np.max(gradient.array) == 1, gradient.array

    degrees = r.gradient(degrees=True, copy=True)
    print(degrees.array)

    assert np.max(degrees.array) == 45, degrees.array

    r = sg.ElevationRaster.from_path(path_two_bands, band_index=(1, 2)).load()
    print(r.band_index)
    print(r._band_index)
    assert r.shape == (2, 101, 101), r.shape

    r = sg.ElevationRaster.from_path(path_two_bands, band_index=None).load()
    assert r.shape == (2, 101, 101), r.shape

    max_ = int(np.nanmax(r.array))
    gradient = r.gradient(copy=True)
    gradient.plot()
    assert max_ == int(np.nanmax(r.array))
    assert int(np.nanmax(gradient.array)) == 17, int(np.nanmax(gradient.array))
    print(np.nanmax(gradient.array))
    degrees = r.gradient(
        degrees=True,
    )
    assert int(np.nanmax(degrees.array)) == 86
    print(np.nanmax(degrees.array))
    assert len(degrees.shape) == 3
    print(degrees.shape)
    print(degrees.array.shape)
    display(degrees.to_gdf())
    gdf = degrees.to_gdf()
    if __name__ == "__main__":
        sg.explore(gdf[gdf["band_index"] == 1], "value")
        sg.explore(gdf[gdf["band_index"] == 2], "value")


def test_zonal():
    r = sg.Raster.from_path(path_singleband, band_index=1).load()
    gdf = sg.make_grid(r.bounds, 100, crs=r.crs)

    gdf.index = [np.random.choice([*"abc"]) for _ in range(len(gdf))]

    zonal_stats = r.zonal(gdf, aggfunc=[sum, np.mean, "median"], raster_calc_func=None)
    assert gdf.index.equals(zonal_stats.index)

    if __name__ == "__main__":
        display(zonal_stats)
        display(gdf)


def test_resize():
    r = sg.Raster.from_path(path_singleband).load()

    assert r.shape == (1, 201, 201), r.shape
    assert r.res == (10, 10), r.res
    r = sg.Raster.from_path(path_singleband).load(res=20)
    assert r.shape == (1, 100, 100), r.shape
    r = sg.Raster.from_path(path_singleband).load(res=30)
    assert r.shape == (1, 67, 67), r.shape

    r = sg.Raster.from_path(path_singleband, band_index=1).load()
    assert r.shape == (201, 201), r.shape
    r = sg.Raster.from_path(path_singleband, band_index=1).load(
        res=20,
    )
    assert r.shape == (100, 100), r.shape
    r = sg.Raster.from_path(path_singleband, band_index=1).load(
        res=30,
    )
    assert r.shape == (67, 67), r.shape

    r = sg.Raster.from_path(path_singleband).load()
    assert r.shape == (1, 201, 201), r.shape
    assert r.res == (10, 10), r.res

    r5 = r.copy().upscale(2)
    assert r5.shape == (1, 402, 402), r5.shape
    assert r5.res == (5, 5), r5.res

    r20 = r.copy().downscale(2)
    assert r20.shape == (1, 101, 101), r20.shape
    assert tuple(int(x) for x in r20.res) == (19, 19), r20.res

    r30 = r.copy().downscale(3)
    assert r30.shape == (1, 67, 67), r30.shape
    assert r30.res == (30, 30), r30.res

    assert r5.unary_union.equals(r.unary_union)
    assert r20.unary_union.equals(r.unary_union)
    assert r30.unary_union.equals(r.unary_union)


def test_clip():
    r = sg.Raster.from_path(path_singleband, nodata=0)

    assert r.shape == (1, 201, 201), r.shape

    circle = r.unary_union.centroid.buffer(100)

    clipped = r.copy().clip(circle)
    assert clipped.shape == (1, 20, 20), clipped.shape

    clipped_xarray = r.copy().load().clip(circle)
    assert np.array_equal(clipped_xarray.array, clipped.array)
    assert clipped_xarray.equals(clipped)

    # masks outside should return nodata on area outside of mask
    southeast_corner = sg.to_gdf(r.bounds[:2], crs=r.crs)
    square_in_corner = sg.to_gdf(southeast_corner.buffer(400).total_bounds, crs=r.crs)

    clipped = r.copy().load().clip(square_in_corner)
    sg.explore(clipped.to_gdf(), r.load().to_gdf())
    assert clipped.array.min() == 0, clipped.array.min()
    assert int(clipped.array.mean()) == 37, clipped.array.mean()
    assert int(clipped.array.max()) == 190, clipped.array.max()

    intersected = clipped.to_gdf().overlay(square_in_corner)

    same_area = (
        int(clipped.area.sum())
        == int(square_in_corner.area.sum())
        == int(intersected.area.sum())
    )
    assert same_area

    clipped2 = (
        r.copy().to_crs(25832).clip(square_in_corner.to_crs(25832)).to_crs(25832)
    ).to_crs(25833)
    sg.explore(clipped.to_gdf(), clipped2.to_gdf())
    sss


def test_convertion():
    r = sg.Raster.from_path(path_singleband, band_index=1).load()
    assert isinstance(r, sg.Raster)

    r2 = sg.ElevationRaster(r)
    assert isinstance(r2, sg.ElevationRaster)

    arr = r.array
    r_from_array = sg.Raster.from_array(arr, **r.profile)

    gdf = r.to_gdf(column="val")

    # multiple columns give multiple bands
    gdf["val_x2"] = gdf["val"] * -1
    r_from_gdf = sg.Raster.from_gdf(gdf, columns=["val", "val_x2"], res=r.res)
    assert r_from_gdf.shape == (2, 201, 201)

    r_from_gdf = sg.Raster.from_gdf(gdf, columns="val", res=r.res)
    assert r_from_gdf.shape == (201, 201)
    assert r_from_gdf.name == "val"

    # putting three 2-dimensional array on top of each other
    r3 = sg.Raster.from_array(
        np.array([r.array, r_from_array.array, r_from_gdf.array]), **r.profile
    )
    assert r3.count == 3, r3.count
    assert r3.shape == (3, 201, 201), r3.shape
    assert r3.bounds == r.bounds

    r3_as_gdf = r3.to_gdf()
    assert r3_as_gdf["band_index"].isin([1, 2, 3]).all()
    assert all(x in list(r3_as_gdf["band_index"]) for x in [1, 2, 3])


def test_res():
    r = sg.Raster.from_path(path_singleband, band_index=1)
    mask_utm33 = sg.to_gdf(box(*r.bounds), crs=r.crs)

    for _ in range(5):
        r = sg.Raster.from_path(path_singleband, band_index=1)
        mask_utm33["geometry"] = mask_utm33.sample_points(5).buffer(100)
        r = r.clip(mask_utm33)
        assert r.res == (10, 10), r.res


def test_to_crs():
    r = sg.Raster.from_path(path_singleband, band_index=1)
    mask_utm33 = sg.to_gdf(box(*r.bounds), crs=r.crs).centroid.buffer(50)
    r = r.clip(mask=mask_utm33)
    r = r.to_crs(25832)

    mask_utm32 = mask_utm33.to_crs(25832)
    assert r.to_gdf().intersects(mask_utm32.unary_union).any()

    r = r.to_crs(25833)
    assert r.to_gdf().intersects(mask_utm33.unary_union).any()

    original = sg.Raster.from_path(path_singleband, band_index=1).load()
    assert original.to_gdf().intersects(r.unary_union).any()


def test_indexes_and_shape():
    # specifying single index is only thing that returns 2dim ndarray
    r = sg.Raster.from_path(path_singleband, band_index=1)
    assert len(r.shape) == 2, r.shape
    assert r.shape == (201, 201), r.shape

    r = sg.Raster.from_path(path_singleband, band_index=(1,))
    assert len(r.shape) == 3, r.shape
    assert r.shape[0] == 1, r.shape

    r = sg.Raster.from_path(path_singleband)
    assert len(r.shape) == 3, r.shape
    assert r.shape[0] == 1, r.shape

    r2 = sg.Raster.from_path(path_two_bands)
    assert len(r2.shape) == 3, r2.shape
    assert r2.shape[0] == 2, r2.shape
    r2 = r2.load()
    assert len(r2.shape) == 3, r2.shape
    assert r2.shape[0] == 2, r2.shape


def test_xarray():
    r = sg.Raster.from_path(path_two_bands)
    xarr = r.load().to_xarray()
    print(xarr)

    r = sg.Raster.from_path(path_singleband, band_index=1)
    xarr = r.load().to_xarray()
    assert isinstance(xarr, xr.DataArray)

    print(r.bounds)
    print(xarr)
    print(xarr.to_dataset())

    print(xarr * 2)


def not_test_raster():
    testpath = testdata + "/res30.tif"
    r = sg.Raster.from_path(path_singleband, band_index=1).load()

    x = 3

    r2 = r.copy()
    shape = int(r2.shape[0] / (r2.shape[0] / x)), int(r2.shape[1] / (r2.shape[1] / x))
    r2.array = skimage.measure.block_reduce(r2.array, shape, np.mean)
    print(r2.array.shape, r.array.shape)
    print(r2.res, r.res)
    print(r2.bounds, r.bounds)
    assert r2.res == (30, 30)
    assert r2.bounds == r.bounds
    r2.write(testpath)


def save_two_band_image():
    r = sg.Raster.from_path(path_singleband, band_index=1)

    mask = sg.to_gdf(r.unary_union, crs=r.crs).buffer(-500)
    r = r.clip(mask)
    r.array[r.array < 0] = 0

    r2 = r * -1
    r2.array = np.array([r.array, r2.array])
    assert len(r2.shape) == 3, r2.shape
    assert r2.shape[0] == 2, r2.shape
    r2.plot()
    r = sg.Raster.from_path(path_two_bands).load()
    r2.write(path_two_bands)

    r2 = sg.Raster.from_path(path_two_bands)
    assert r2.shape[0] == 2, r2.shape
    r2 = r2.load()
    assert r2.shape[0] == 2, r2.shape
    r2.plot()


if __name__ == "__main__":
    # save_two_band_image()

    test_xarray()
    test_resize()
    test_convertion()

    test_transform()

    test_indexes_and_shape()

    test_to_crs()
    test_clip()
    test_elevation()
    test_zonal()
    test_sample()
    test_res()

    not_test_raster()

    print("ferdig")
