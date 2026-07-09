"""Activity-diagram conversion from BUML to WME (Apollon) JSON format.

Symmetric counterpart of ``activity_diagram_processor``. Because the frontend
diagram is thinner than the metamodel, several distinct node classes **collapse**
onto one frontend type:

* :class:`DecisionNode` and :class:`MergeNode` -> ``ActivityMergeNode`` (diamond)
* :class:`ForkNode` and :class:`JoinNode` -> ``ActivityForkNode`` (bar)
* :class:`ActivityFinalNode` and :class:`FlowFinalNode` -> ``ActivityFinalNode``

The topology (fan-in vs fan-out) that the processor used to disambiguate them is
preserved by the edges, so a diamond written as a decision comes back as a
decision on re-import. Guards ride on the control-flow edge ``name``.
"""

import ast
import logging
import uuid

from besser.BUML.metamodel.activity.activity import (
    ActivityModel,
    InitialNode,
    FinalNode,
    Action,
    DecisionNode,
    MergeNode,
    ForkNode,
    JoinNode,
)
from besser.utilities.web_modeling_editor.backend.services.utils import (
    determine_connection_direction,
    calculate_connection_points,
    calculate_path_points,
    calculate_relationship_bounds,
)

logger = logging.getLogger(__name__)

# Reverse of the processor's mapping. Order matters: FinalNode/Action are checked
# before their abstract siblings via isinstance in _frontend_type.
INITIAL_TYPE = "ActivityInitialNode"
FINAL_TYPE = "ActivityFinalNode"
ACTION_TYPE = "ActivityActionNode"
MERGE_TYPE = "ActivityMergeNode"
FORK_TYPE = "ActivityForkNode"
CONTROL_FLOW_TYPE = "ActivityControlFlow"


def _frontend_type(node) -> str:
    """Map a metamodel node to its frontend (Apollon) element type string."""
    if isinstance(node, InitialNode):
        return INITIAL_TYPE
    if isinstance(node, FinalNode):
        return FINAL_TYPE
    if isinstance(node, Action):
        return ACTION_TYPE
    if isinstance(node, (DecisionNode, MergeNode)):
        return MERGE_TYPE
    if isinstance(node, (ForkNode, JoinNode)):
        return FORK_TYPE
    return ACTION_TYPE  # defensive fallback; unreachable for v1 node set


def _display_name(node) -> str:
    """The frontend display ``name``: the raw ``label`` if set, else the identifier."""
    return node.label if node.label is not None else node.name


def _node_bounds(node, index: int) -> dict:
    """Reuse the round-tripped bounds if present, else synthesize a simple grid slot."""
    layout = node.layout or {}
    if isinstance(layout.get("bounds"), dict):
        return layout["bounds"]
    col, row = index % 5, index // 5
    return {"x": -600 + col * 220, "y": -300 + row * 160, "width": 160, "height": 60}


def _edge_name(edge) -> str:
    """The frontend edge ``name``: the guard body, else the round-tripped label, else ''.

    A guard is surfaced only when the source is a :class:`DecisionNode` -- that is
    exactly the condition under which the processor reads a name back as a guard,
    so the mapping stays symmetric even for hand-built models that (invalidly)
    put a guard on a non-decision edge.
    """
    if edge.guard is not None and edge.guard.body and isinstance(edge.source, DecisionNode):
        return edge.guard.body
    if edge.is_default:
        return ""  # default "else" branch carries no label
    layout = edge.layout or {}
    return layout.get("name") or ""


def activity_object_to_json(model: ActivityModel) -> dict:
    """Convert an :class:`ActivityModel` into WME Activity diagram JSON.

    Note: the frontend has no field for an action ``body`` or the class binding,
    so those are intentionally NOT serialized (Phase-1 thin-frontend gap). The
    builder / AST importer keep them for BUML<->code fidelity, but they do not
    survive a trip through this JSON layer.

    Args:
        model: An ActivityModel metamodel instance.

    Returns:
        Dictionary in the frontend JSON format for activity diagrams.
    """
    elements: dict = {}
    relationships: dict = {}
    id_of: dict = {}  # node -> element id

    # Stable node ordering so synthesized layout and ids are deterministic.
    ordered_nodes = sorted(model.nodes, key=lambda n: n.name)

    for index, node in enumerate(ordered_nodes):
        layout = node.layout or {}
        node_id = layout.get("id") or str(uuid.uuid4())
        id_of[node] = node_id
        elements[node_id] = {
            "id": node_id,
            "name": _display_name(node),
            "type": _frontend_type(node),
            "owner": layout.get("owner"),
            "bounds": _node_bounds(node, index),
        }

    for edge in sorted(model.edges, key=lambda e: e.name):
        if edge.source is None or edge.target is None:
            continue
        source_id = id_of.get(edge.source)
        target_id = id_of.get(edge.target)
        if source_id is None or target_id is None:
            continue

        source_bounds = elements[source_id]["bounds"]
        target_bounds = elements[target_id]["bounds"]
        source_dir, target_dir = determine_connection_direction(source_bounds, target_bounds)
        source_point = calculate_connection_points(source_bounds, source_dir)
        target_point = calculate_connection_points(target_bounds, target_dir)
        path_points = calculate_path_points(source_point, target_point, source_dir, target_dir)
        rel_bounds = calculate_relationship_bounds(path_points)

        rel_id = (edge.layout or {}).get("id") or str(uuid.uuid4())
        relationships[rel_id] = {
            "id": rel_id,
            "name": _edge_name(edge),
            "type": CONTROL_FLOW_TYPE,
            "owner": None,
            "bounds": rel_bounds,
            "path": path_points,
            "source": {
                "direction": source_dir,
                "element": source_id,
                "bounds": {"x": source_point["x"], "y": source_point["y"], "width": 0, "height": 0},
            },
            "target": {
                "direction": target_dir,
                "element": target_id,
                "bounds": {"x": target_point["x"], "y": target_point["y"], "width": 0, "height": 0},
            },
            "isManuallyLayouted": False,
        }

    return {
        "version": "3.0.0",
        "type": "ActivityDiagram",
        "size": {"width": 1400, "height": 640},
        "interactive": {"elements": {}, "relationships": {}},
        "elements": elements,
        "relationships": relationships,
        "assessments": {},
    }


# --------------------------------------------------------------------------- #
# Legacy file-import entry point (AST-based, for /get-json-model)
# --------------------------------------------------------------------------- #

def _const(node):
    """Return the literal value of an ``ast`` constant node, or None."""
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _kw(call: ast.Call, name: str):
    """Return the literal value of keyword ``name`` on ``call``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return _const(kw.value)
    return None


def activity_to_json(content: str) -> dict:
    """Convert activity-builder Python source into WME JSON (file-import path).

    AST-parses the ``ActivityModel`` / ``new_*`` / ``connect`` calls emitted by
    :func:`activity_model_to_code` and reconstructs an :class:`ActivityModel`
    **without executing** the uploaded file, then reuses
    :func:`activity_object_to_json`. Unrecognised statements are ignored.

    Args:
        content: Python source of a BUML activity model.

    Returns:
        Dictionary in the frontend JSON format for activity diagrams.
    """
    tree = ast.parse(content)

    model_name = "Imported_Activity"
    node_specs = []          # (var, factory_name, ast.Call)
    label_of = {}            # var -> label str
    connect_calls = []       # list[ast.Call]

    for stmt in ast.walk(tree):
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            target = stmt.targets[0] if stmt.targets else None
            if isinstance(call.func, ast.Name) and call.func.id == "ActivityModel":
                model_name = _kw(call, "name") or model_name
            elif (isinstance(call.func, ast.Attribute)
                  and call.func.attr.startswith("new_")
                  and isinstance(target, ast.Name)):
                node_specs.append((target.id, call.func.attr, call))
        elif isinstance(stmt, ast.Assign):
            target = stmt.targets[0] if stmt.targets else None
            if (isinstance(target, ast.Attribute) and target.attr == "label"
                    and isinstance(target.value, ast.Name)):
                label_of[target.value.id] = _const(stmt.value)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "connect":
                connect_calls.append(call)

    model = ActivityModel(name=model_name)
    var_to_node = {}
    for var, factory_name, call in node_specs:
        factory = getattr(model, factory_name, None)
        if factory is None:
            logger.warning("Unknown activity factory '%s'; skipping node '%s'.", factory_name, var)
            continue
        name = _kw(call, "name") or var
        body = _kw(call, "body") if factory_name == "new_action" else None
        node = factory(name=name, body=body) if body else factory(name=name)
        if var in label_of and label_of[var] is not None:
            node.label = label_of[var]
        var_to_node[var] = node

    for call in connect_calls:
        if len(call.args) < 2:
            continue
        src = var_to_node.get(call.args[0].id) if isinstance(call.args[0], ast.Name) else None
        tgt = var_to_node.get(call.args[1].id) if isinstance(call.args[1], ast.Name) else None
        if src is None or tgt is None:
            continue
        model.connect(
            src, tgt,
            guard=_kw(call, "guard"),
            is_default=bool(_kw(call, "is_default")),
            weight=_kw(call, "weight") or 1,
            name=_kw(call, "name"),
        )

    return activity_object_to_json(model)
