# %%
import cProfile

import sgis as sg


def count_function_calls(points_oslo, roads_oslo):
    p = points_oslo
    p = p.iloc[:50]
    p["idx"] = p.index
    p["idx2"] = p.index

    r = roads_oslo

    nw = sg.remove_isolated_networks(r)
    nw = sg.make_directed_network_norway(nw)

    nw = (
        nw.get_component_size()
        .get_connected_components()
        .close_network_holes(1.1)
        .remove_isolated()
        .cut_lines(250)
    )

    rules = sg.NetworkAnalysisRules(weight="minutes")
    nwa = sg.NetworkAnalysis(nw, rules=rules)
    nwa.network = nwa.network.get_component_size()
    nwa.network = nwa.network.remove_isolated()

    for _ in range(10):
        nwa.od_cost_matrix(p.sample(1), p.sample(1))


def main():
    from oslo import points_oslo
    from oslo import roads_oslo

    count_function_calls(points_oslo, roads_oslo)
    cProfile.run("count_function_calls()", sort="cumtime")


if __name__ == "__main__":
    main()
