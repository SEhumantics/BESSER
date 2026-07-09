"""
Activity Model Builder

Generates Python code from an :class:`ActivityModel` metamodel instance.
The generated code can be ``exec()``'d to recreate the ActivityModel.

Scope (Phase 1): control-flow only -- nodes, control-flow edges, and guards.
Class binding (``ref_class``/``ref_method``/``ref_property``) is intentionally
NOT emitted; it has no representation in the web editor yet and is deferred to a
later phase.
"""

import re

from besser.BUML.metamodel.activity.activity import (
    ActivityModel,
    InitialNode,
    ActivityFinalNode,
    FlowFinalNode,
    OpaqueAction,
    DecisionNode,
    MergeNode,
    ForkNode,
    JoinNode,
)
from besser.utilities.buml_code_builder.common import _escape_python_string

_BANNER = [
    "##################",
    "# ACTIVITY MODEL #",
    "##################",
]

# metamodel node class -> ActivityModel factory method name
_FACTORY_OF = {
    InitialNode: "new_initial",
    ActivityFinalNode: "new_activity_final",
    FlowFinalNode: "new_flow_final",
    OpaqueAction: "new_action",
    DecisionNode: "new_decision",
    MergeNode: "new_merge",
    ForkNode: "new_fork",
    JoinNode: "new_join",
}


def _sanitize_identifier(name: str) -> str:
    """Sanitize a string into a valid Python identifier stem (never empty)."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name or "")
    sanitized = re.sub(r"^[^a-zA-Z_]+", "", sanitized)
    return sanitized or "node"


def _assign_var_names(nodes) -> dict:
    """Map each node to a unique, valid Python variable name.

    ``NamedElement.name`` only rejects spaces/hyphens, so a metamodel-legal name
    can still be an invalid identifier (e.g. ``"1st"``). We sanitize into a valid
    stem and de-duplicate, so the generated code always parses even for models
    built directly in code rather than via the (sanitizing) JSON processor.
    """
    used: set = set()
    var_of: dict = {}
    for node in nodes:
        stem = _sanitize_identifier(node.name)
        candidate = f"{stem}_node"
        i = 1
        while candidate in used:
            i += 1
            candidate = f"{stem}_{i}_node"
        used.add(candidate)
        var_of[node] = candidate
    return var_of


def _node_lines(node, var: str, model_var: str) -> list:
    """Emit the factory call (and optional label) for one node."""
    factory = _FACTORY_OF.get(type(node))
    if factory is None:
        return []  # unknown/abstract node type; skip defensively
    args = [f"name='{_escape_python_string(node.name)}'"]
    if isinstance(node, OpaqueAction) and node.body is not None and node.body.body:
        args.append(f"body='{_escape_python_string(node.body.body)}'")
    lines = [f"{var} = {model_var}.{factory}({', '.join(args)})"]
    if node.label is not None:
        lines.append(f"{var}.label = '{_escape_python_string(node.label)}'")
    return lines


def _edge_line(edge, var_of: dict, model_var: str):
    """Emit the ``connect(...)`` call for one edge, or None if it cannot be emitted."""
    if edge.source not in var_of or edge.target not in var_of:
        return None
    args = [var_of[edge.source], var_of[edge.target]]
    if edge.guard is not None and edge.guard.body:
        args.append(f"guard='{_escape_python_string(edge.guard.body)}'")
    if edge.is_default:
        args.append("is_default=True")
    if edge.weight != 1:
        args.append(f"weight={edge.weight}")
    args.append(f"name='{_escape_python_string(edge.name)}'")
    return f"{model_var}.connect({', '.join(args)})"


def activity_model_to_code(model: ActivityModel, file_path: str = None,
                           model_var_name: str = "activity") -> str:
    """Generate Python code from an :class:`ActivityModel` instance.

    Args:
        model: The ActivityModel instance to convert.
        file_path: Optional path to write the generated code to.
        model_var_name: Variable name to use for the model (default: "activity").

    Returns:
        The generated Python code as a string.
    """
    # Initial nodes first for readability (order is functionally irrelevant).
    ordered_nodes = sorted(
        model.nodes, key=lambda n: (not isinstance(n, InitialNode), n.name)
    )
    var_of = _assign_var_names(ordered_nodes)

    code_lines = list(_BANNER)
    code_lines.append("")
    code_lines.append("from besser.BUML.metamodel.activity.activity import ActivityModel")
    code_lines.append("")
    code_lines.append(
        f"{model_var_name} = ActivityModel(name='{_escape_python_string(model.name)}')"
    )
    code_lines.append("")

    for node in ordered_nodes:
        code_lines.extend(_node_lines(node, var_of[node], model_var_name))
    code_lines.append("")

    for edge in sorted(model.edges, key=lambda e: e.name):
        line = _edge_line(edge, var_of, model_var_name)
        if line is not None:
            code_lines.append(line)
    code_lines.append("")

    result = "\n".join(code_lines)

    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(result)

    return result
