# ssb-gis-utils

## Network analysis

The package supports three types of network analysis, and methods for customising and optimising your road data.

Analysis can start by initialising a NetworkAnalysis instance:

```python
from gis_utils import DirectedNetwork, NetworkAnalysisRules, NetworkAnalysis

roads = gpd.read_parquet("tests/testdata/roads_oslo_2022.parquet")

nw = (
    DirectedNetwork(roads)
    .remove_isolated()
    .make_directed_network(
        direction_col="oneway",
        direction_vals_bft=("B", "FT", "TF"),
        minute_cols=("drivetime_fw", "drivetime_bw"),
        )
)

rules = NetworkAnalysisRules(weight="minutes")

nwa = NetworkAnalysis(
    network=nw, rules=rules
)

nwa
```

    NetworkAnalysis(network=DirectedNetwork(6364 km), rules=NetworkAnalysisRules(weight='minutes', search_tolerance=250, search_factor=10, ...))

```python
points = gpd.read_parquet("tests/testdata/random_points.parquet")
p1 = points.iloc[[0]]
```

### OD cost matrix

Fast many-to-many travel times/distances

```python
od = nwa.od_cost_matrix(p1, points, lines=True)

print(od.head(3))

gs.qtm(od, "minutes", title="Travel time (minutes) from 1 to 1000 points.", **plot_kwargs,
)
```

      origin destination    minutes  \
    0  79166       79167   0.000000
    1  79166       79168  12.930588
    2  79166       79169  10.867076

                                                geometry
    0  LINESTRING (263122.700 6651184.900, 263122.700...
    1  LINESTRING (263122.700 6651184.900, 272456.100...
    2  LINESTRING (263122.700 6651184.900, 270082.300...

![png](tests/examples_files/examples_4_1.png)

### Shortest path

Get the actual paths, either individually or summarised:

```python
sp = nwa.shortest_path(points.sample(100), points.sample(100), summarise=True)

gs.qtm(
    gs.buff(sp, 15),
    "n",
    scheme="naturalbreaks",
    cmap="plasma",
    title="Number of times each road was used.",
    **plot_kwargs,
)
```

![png](tests/examples_files/examples_6_0.png)

### Service area

Get the area that can be reached within one or more breaks

```python
sa = nwa.service_area(p1, breaks=np.arange(1, 11), dissolve=False)

sa = sa.drop_duplicates(["source", "target"])

gs.qtm(sa, "minutes", k=10, title="Roads that can be reached within 1 to 10 minutes", legend=False, **plot_kwargs)
```

![png](tests/examples_files/examples_8_0.png)

## Developer information

### Git LFS

The data in the testdata directory is stored with [Git LFS](https://git-lfs.com/).
Make sure `git-lfs` is installed and that you have run the command `git lfs install`
at least once. You only need to run this once per user account.

### Dependencies

[Poetry](https://python-poetry.org/) is used for dependency management. Install
poetry and run the command below from the root directory to install the dependencies.

```shell
poetry install --no-root
```

### Tests

Use the following command from the root directory to run the tests:

```shell
poetry run pytest  # from root directory
```

#### Jupyter Notebooks

The files ending with `_ipynb.py` in the tests directory are jupyter notebooks
stored as plain python files, using `jupytext`. To open them as Jupyter notebooks,
right-click on them in JupyterLab and select Open With &rarr; Notebook.

When testing locally, start JupyterLab with this command:

```shell
poetry run jupter lab
```

For VS Code there are extensions for opening a python script as Jupyter Notebook,
for example:
[Jupytext for Notebooks](https://marketplace.visualstudio.com/items?itemName=donjayamanne.vscode-jupytext).

### Formatting

Format the code with `black` and `isort` by running the following command from the
root directory:

```shell
poetry run black .
poetry run isort .
```

### Pre-commit hooks

We are using [pre-commit hooks](https://pre-commit.com/) to make sure the code is
correctly formatted and consistent before committing. Use the following command from
the root directory in the repo to install the pre-commit hooks:

```shell
poetry run pre-commit install
```

It then checks the changed files before committing. You can run the pre-commit checks
on all files by using this command:

```shell
poetry run pre-commit run --all-files
```
