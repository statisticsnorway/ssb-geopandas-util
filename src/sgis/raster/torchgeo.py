import glob
import os
import warnings
from typing import Iterable

import rasterio
import rasterio.merge
from rasterio.io import DatasetReader
from rasterio.vrt import WarpedVRT
from torchgeo.datasets.geo import RasterDataset
from torchgeo.datasets.sentinel import Sentinel2 as TorchgeoSentinel2


try:
    import dapla as dp
except ImportError:
    pass

try:
    from gcsfs.core import GCSFile
except ImportError:

    class GCSFile:
        pass


from ..io._is_dapla import is_dapla
from ..io.opener import opener
from .bands import SENTINEL2_FILENAME_REGEX


class GCSRasterDataset(RasterDataset):
    """Wrapper around torchgeo's RasterDataset that works in and outside of Dapla (stat norway)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if is_dapla():
            [file.close() for file in self.files]

    @property
    def files(self) -> set[GCSFile] | set[str]:
        """A list of all files in the dataset.

        Returns:
            All files in the dataset.

        .. versionadded:: 0.5
        """
        if isinstance(self.paths, str):
            paths: list[str] = [self.paths]
        else:
            paths = self.paths

        if is_dapla():
            fs = dp.FileClient.get_gcs_file_system()
            files: set[GCSFile] = {
                fs.open(x)
                for x in _get_gcs_paths(
                    paths, filename_glob=self.filename_glob, file_system=fs
                )
            }
            return files

        # Using set to remove any duplicates if directories are overlapping
        files: set[str] = set()
        for path in paths:
            if os.path.isdir(path):
                pathname = os.path.join(path, "**", self.filename_glob)
                files |= {
                    x for x in glob.iglob(pathname, recursive=True) if os.path.isfile(x)
                }
            elif os.path.isfile(path):
                files.add(path)
            else:
                warnings.warn(
                    f"Could not find any relevant files for provided path '{path}'. "
                    f"Path was ignored.",
                    UserWarning,
                )

        return files

    def _load_warp_file(self, filepath: str) -> DatasetReader:
        """Load and warp a file to the correct CRS and resolution.

        Args:
            filepath: file to load and warp

        Returns:
            file handle of warped VRT
        """
        with opener(filepath) as f:
            src = rasterio.open(f)

            # Only warp if necessary
            if src.crs != self.crs:
                vrt = WarpedVRT(src, crs=self.crs)
                src.close()
                return vrt
            else:
                return src


def _get_gcs_paths(
    paths: str | Iterable[str], filename_glob: str, file_system=None
) -> set[str]:
    if file_system is None:
        file_system = dp.FileClient.get_gcs_file_system()

    # Using set to remove any duplicates if directories are overlapping
    out_paths: set[str] = set()
    for path in paths:
        pathname = os.path.join(path, "**", filename_glob)
        if is_dapla():
            out_paths |= {
                x for x in file_system.glob(pathname, recursive=True) if "." in x
            }
    return out_paths


class Sentinel2(GCSRasterDataset):
    """Works like torchgeo's Sentinel2, with custom regexes."""

    date_format: str = "%Y%m%d"
    filename_glob = "SENTINEL2X_*_*.*"

    filename_regex = SENTINEL2_FILENAME_REGEX

    all_bands = [
        # "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "B6",
        "B7",
        "B8",
        "B8A",
        # "B9",
        # "B10",
        "B11",
        "B12",
    ]
    rgb_bands = ["B4", "B3", "B2"]

    separate_files = True

    cmap: dict[int, tuple[int, int, int, int]] = {}

    plot = TorchgeoSentinel2.plot
