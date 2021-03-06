"""
Contains code for visualizing Bionic flow graphs.  Importing this module will
pull in several optional dependencies as well.  The external Graphviz library
is also required.
"""

from pathlib import Path
from collections import defaultdict
from io import BytesIO, IOBase

from .deps.optdep import import_optional_dependency
from .utils.misc import rewrap_docstring

module_purpose = "rendering the flow DAG"
hsluv = import_optional_dependency("hsluv", purpose=module_purpose)
pydot = import_optional_dependency("pydot", purpose=module_purpose)
Image = import_optional_dependency("PIL.Image", purpose=module_purpose)


class FlowImage:
    def __init__(self, pydot_graph):
        """
        Given a pydot graph object, create Pillow Image or SVG represented as XML text.
        Replicates the PIL APIs for save and show, for both PIL-supported and SVG formats.
        """
        self._pil_image = Image.open(BytesIO(pydot_graph.create_png()))
        self._xml_bytes = pydot_graph.create_svg()

    def save(self, fp, format=None, **params):
        """
        Save flow visualization to filename, Path, or file object. If file object is passed,
        must also pass format. Pass additional keyword options supported by PIL using params.
        Args:
            fp: Filename (string), pathlib.Path object, or file object
            format: format parameters
            **params: additional keyword options supported by PIL
        """
        is_file_object = isinstance(fp, IOBase)
        use_svg = (format == "svg") or (
            format is None and not is_file_object and Path(fp).suffix == ".svg"
        )
        if use_svg:
            if is_file_object:
                fp.write(self._xml_bytes)
            else:
                with open(fp, "wb") as file:
                    file.write(self._xml_bytes)
        else:
            self._pil_image.save(fp, format, **params)

    def show(self):
        """Show image using PIL"""
        self._pil_image.show()

    def _repr_svg_(self):
        """Rich display image as SVG in IPython notebook or Qt console."""
        return self._xml_bytes.decode("utf8")


def hpluv_color_dict(keys, saturation, lightness):
    """
    Given a list of arbitary keys, generates a dict mapping those keys to a set
    of evenly-spaced, perceptually uniform colors with the specified saturation
    and lightness.
    """

    n = len(keys)
    color_strs = [
        hsluv.hpluv_to_hex([(360 * (i / float(n))), saturation, lightness])
        for i in range(n)
    ]
    return dict(zip(keys, color_strs))


def dot_from_graph(graph, vertical=False, curvy_lines=False, name=None):
    """
    Given a NetworkX directed acyclic graph, returns a Pydot object which can
    be visualized using GraphViz.
    """

    if name is None:
        graph_name = ""
    else:
        graph_name = name

    dot = pydot.Dot(
        graph_name=graph_name,
        graph_type="digraph",
        splines="spline" if curvy_lines else "line",
        outputorder="edgesfirst",
        rankdir="TB" if vertical else "LR",
    )

    # First, we cluster together any nodes that share an entity name. This includes
    # nodes generated by a common tuple function, and nodes that differ only by case
    # key.
    node_clusters_by_entity_name = defaultdict(list)
    for node in graph.nodes():
        entity_names = list(node.dnode.all_entity_names())
        # If this node has no entity names at all, we'll pretend it has a single entity
        # name. (I don't think this can currently happen, because the only descriptor
        # with no entity names is the empty tuple `()`, and specifying an empty tuple
        # as an output descriptor ends up doing nothing. Still, we'll try to handle this
        # gracefully in case things change.)
        if len(entity_names) == 0:
            entity_names = [""]

        # If this node has multiple entity names, we want to make sure all those names
        # are associated with the same cluster, so we'll merge all the clusters we find.
        first_cluster = node_clusters_by_entity_name[entity_names[0]]
        for other_entity_name in entity_names[1:]:
            other_cluster = node_clusters_by_entity_name[other_entity_name]
            if other_cluster is not first_cluster:
                first_cluster.extend(other_cluster)
                node_clusters_by_entity_name[other_entity_name] = first_cluster

        first_cluster.append(node)

    # Now we deduplicate the clusters, arrange them in a deterministic order, and assign
    # a color to each one. (The determinism is important so that the colored graph looks
    # the same each time.)
    unique_node_clusters_by_obj_id = {
        id(cluster): cluster for cluster in node_clusters_by_entity_name.values()
    }
    sorted_node_clusters = sorted(unique_node_clusters_by_obj_id.values(), key=min)
    cluster_ixs = list(range(len(sorted_node_clusters)))
    color_strs_by_cluster_ix = hpluv_color_dict(
        cluster_ixs,
        saturation=99,
        lightness=90,
    )

    def name_from_node(node):
        # We wrap all names in quotes; if we don't, pydot will react to special
        # characters by either adding its own quotes or emitting invalid code. These
        # quotes aren't visible in the actual visualization.
        return '"' + (graph.nodes[node]["name"]) + '"'

    def doc_from_node(node):
        return graph.nodes[node].get("doc")

    for cluster_ix, node_cluster in zip(cluster_ixs, sorted_node_clusters):
        # We use a numerical cluster index instead of something like an entity name
        # because pydot can break if the cluster name constains special characters.
        subdot = pydot.Cluster(str(cluster_ix), style="invis")
        color = color_strs_by_cluster_ix[cluster_ix]

        for node in sorted(node_cluster):
            doc = doc_from_node(node)
            dot_node = pydot.Node(
                name_from_node(node),
                style="filled",
                fillcolor=color,
                shape="box",
            )
            if doc:
                tooltip = rewrap_docstring(doc)
                dot_node.set("tooltip", tooltip)
            subdot.add_node(dot_node)

        dot.add_subgraph(subdot)

    for pred_node in graph.nodes():
        for succ_node in graph.successors(pred_node):
            dot.add_edge(
                pydot.Edge(
                    name_from_node(pred_node),
                    name_from_node(succ_node),
                    arrowhead="open",
                    tailport="s" if vertical else "e",
                )
            )

    return dot
