"""Activity-diagram processing for converting WME JSON to BUML format.

Returns an :class:`ActivityModel` metamodel instance from the frontend (Apollon)
Activity diagram JSON envelope. The frontend diagram is deliberately *thinner*
than the metamodel, so this processor reconciles the two:

* The frontend has only ``ActivityMergeNode`` (a diamond) and ``ActivityForkNode``
  (a bar) -- each is **dual-purpose**. We disambiguate by topology: a diamond that
  fans out (>=2 outgoing) is a :class:`DecisionNode`, one that fans in is a
  :class:`MergeNode`; a bar that fans out is a :class:`ForkNode`, one that fans in
  is a :class:`JoinNode`.
* The only guard carrier in the frontend is the control-flow edge's ``name``. On a
  decision out-branch it becomes the branch guard (an empty name marks the default
  "else" branch); elsewhere it is kept as opaque ``layout`` for round-trip only.
* Node names in the frontend are free display text (spaces/duplicates/empty);
  ``NamedElement`` requires identifier-safe unique names, so we sanitize into
  ``node.name`` and stash the raw display string in ``node.label``.

Like the BPMN processor, this **never calls** :meth:`ActivityModel.validate`; a
mid-edit diagram routinely violates the strict topology rules. Callers validate
separately if they need to.
"""

import logging
import re

from besser.BUML.metamodel.activity.activity import ActivityModel
from besser.utilities.web_modeling_editor.backend.services.exceptions import ConversionError

logger = logging.getLogger(__name__)


# Frontend (Apollon) element/relationship type strings -- see the
# `uml-activity-diagram` package's `ActivityElementType` / `ActivityRelationshipType`.
INITIAL_TYPE = "ActivityInitialNode"
FINAL_TYPE = "ActivityFinalNode"
ACTION_TYPE = "ActivityActionNode"
MERGE_TYPE = "ActivityMergeNode"          # diamond: Decision (fan-out) or Merge (fan-in)
FORK_TYPES = ("ActivityForkNode", "ActivityForkNodeHorizontal")  # bar: Fork or Join
OBJECT_TYPE = "ActivityObjectNode"        # object nodes are deferred in the metamodel
FRAME_TYPE = "Activity"                   # layout container, no metamodel equivalent
CONTROL_FLOW_TYPE = "ActivityControlFlow"

# Types that become metamodel nodes (everything else is skipped).
_NODE_TYPES = {INITIAL_TYPE, FINAL_TYPE, ACTION_TYPE, MERGE_TYPE, *FORK_TYPES}


def _sanitize_identifier(name: str) -> str:
    """Sanitize a string into a valid Python identifier (empty -> '')."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name or "")
    sanitized = re.sub(r"^[^a-zA-Z_]+", "", sanitized)
    return sanitized


def _unique_name(base: str, used: set) -> str:
    """Return an identifier-safe name derived from ``base`` unique within ``used``."""
    candidate = base or "n"
    if candidate in used:
        i = 1
        while f"{candidate}_{i}" in used:
            i += 1
        candidate = f"{candidate}_{i}"
    used.add(candidate)
    return candidate


def _node_layout(elem_id: str, elem: dict) -> dict:
    """Opaque ``layout`` passthrough for a node (round-trips the WME shape)."""
    return {"id": elem_id, "owner": elem.get("owner"), "bounds": elem.get("bounds")}


def _edge_layout(rel_id: str, rel: dict, display_name: str) -> dict:
    """Opaque ``layout`` passthrough for an edge; keeps the raw display name too."""
    return {
        "id": rel_id,
        "owner": rel.get("owner"),
        "bounds": rel.get("bounds"),
        "path": rel.get("path"),
        "name": display_name,
        "source_direction": (rel.get("source") or {}).get("direction"),
        "target_direction": (rel.get("target") or {}).get("direction"),
    }


def process_activity_diagram(json_data: dict) -> ActivityModel:
    """Convert a WME Activity diagram (JSON) into an :class:`ActivityModel`.

    Args:
        json_data: Dictionary with the Apollon envelope; the payload sits under
            ``json_data["model"]`` with ``elements`` (nodes) and ``relationships``
            (control flows) keyed by id.

    Returns:
        ActivityModel: the reconstructed model (not validated).

    Raises:
        ConversionError: if the ``model`` key is missing.
    """
    name = json_data.get("title") or "Generated_Activity_Model"
    # NamedElement rejects spaces and hyphens; a legitimate diagram title like
    # "Order-Flow" would otherwise raise (surfacing as an HTTP 400). Sanitize
    # both into underscores so any title is accepted.
    name = re.sub(r"[ \-]+", "_", name) or "Generated_Activity_Model"

    model_data = json_data.get("model")
    if not model_data:
        raise ConversionError("Activity diagram JSON is missing the 'model' key.")

    elements = model_data.get("elements") or {}
    relationships = model_data.get("relationships") or {}

    activity = ActivityModel(name=name)

    # --- degree bookkeeping: needed to disambiguate diamonds/bars ----------
    # Only edges between elements we actually build as metamodel nodes count
    # toward fan-in/out. Edges to skipped types (object nodes, the Activity
    # frame) or to dangling/deleted ids must NOT inflate a diamond/bar's degree,
    # or a plain pass-through diamond would be misread as a DecisionNode.
    node_ids = {eid for eid, el in elements.items() if el.get("type") in _NODE_TYPES}
    control_flows = [
        (rid, rel) for rid, rel in relationships.items()
        if rel.get("type") == CONTROL_FLOW_TYPE
    ]
    out_deg: dict = {}
    in_deg: dict = {}
    for _, rel in control_flows:
        src = (rel.get("source") or {}).get("element")
        tgt = (rel.get("target") or {}).get("element")
        if src in node_ids and tgt in node_ids:
            out_deg[src] = out_deg.get(src, 0) + 1
            in_deg[tgt] = in_deg.get(tgt, 0) + 1

    # --- Pass 1: build node objects, mapping element id -> node ------------
    node_by_id: dict = {}
    used_names: set = set()

    for elem_id, elem in elements.items():
        elem_type = elem.get("type")
        if elem_type not in _NODE_TYPES:
            if elem_type in (OBJECT_TYPE, FRAME_TYPE):
                logger.info("Activity element '%s' of type '%s' is not part of the "
                            "control-flow metamodel; skipping.", elem_id, elem_type)
            else:
                logger.warning("Activity element '%s' has unknown type '%s'; skipping.",
                               elem_id, elem_type)
            continue

        raw_name = elem.get("name", "") or ""
        base = _sanitize_identifier(raw_name)

        if elem_type == INITIAL_TYPE:
            node = activity.new_initial(_unique_name(base or "initial", used_names))
        elif elem_type == FINAL_TYPE:
            node = activity.new_activity_final(_unique_name(base or "final", used_names))
        elif elem_type == ACTION_TYPE:
            node = activity.new_action(_unique_name(base or "action", used_names))
        elif elem_type == MERGE_TYPE:
            if out_deg.get(elem_id, 0) >= 2:
                node = activity.new_decision(_unique_name(base or "decision", used_names))
            else:
                node = activity.new_merge(_unique_name(base or "merge", used_names))
        else:  # fork bar
            if out_deg.get(elem_id, 0) >= 2:
                node = activity.new_fork(_unique_name(base or "fork", used_names))
            else:
                node = activity.new_join(_unique_name(base or "join", used_names))

        node.label = raw_name          # raw display text (round-trips as JSON "name")
        node.layout = _node_layout(elem_id, elem)
        node_by_id[elem_id] = node

    # --- Pass 2: build control-flow edges ---------------------------------
    from besser.BUML.metamodel.activity.activity import DecisionNode  # local: avoid top clutter

    for rel_id, rel in control_flows:
        src = node_by_id.get((rel.get("source") or {}).get("element"))
        tgt = node_by_id.get((rel.get("target") or {}).get("element"))
        if src is None or tgt is None:
            logger.warning("Activity flow '%s' has a dangling endpoint; skipping.", rel_id)
            continue

        display_name = rel.get("name", "") or ""
        guard = None
        is_default = False
        # The edge name is a guard only on a decision out-branch; an empty name
        # there marks the default "else". Elsewhere it is layout-only.
        if isinstance(src, DecisionNode):
            if display_name:
                guard = display_name
            else:
                is_default = True

        edge = activity.connect(src, tgt, guard=guard, is_default=is_default)
        edge.layout = _edge_layout(rel_id, rel, display_name)

    return activity
