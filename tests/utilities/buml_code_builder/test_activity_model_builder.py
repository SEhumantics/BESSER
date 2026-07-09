"""Tests for the activity code builder.

Verifies the generated Python parses, exec's back into an equivalent
``ActivityModel``, is deterministic, and stays within Phase-1 scope (no class
binding emitted).
"""

from __future__ import annotations

from besser.BUML.metamodel.activity.activity import (
    ActivityModel,
    DecisionNode,
    ForkNode,
    JoinNode,
    MergeNode,
    OpaqueAction,
    InitialNode,
    ActivityFinalNode,
)
from besser.utilities.buml_code_builder.activity_model_builder import activity_model_to_code


def _sample_model() -> ActivityModel:
    """initial -> validate -> decision -[approved/rejected]-> approve/reject
    -> merge -> fork -> logIt/notify -> join -> final."""
    m = ActivityModel(name="ApprovalActivity")
    ini = m.new_initial("initial")
    validate = m.new_action("validate")
    decision = m.new_decision("decision")
    approve = m.new_action("approve")
    reject = m.new_action("reject")
    merge = m.new_merge("merge")
    fork = m.new_fork("fork")
    log_it = m.new_action("logIt")
    notify = m.new_action("notify")
    join = m.new_join("join")
    final = m.new_activity_final("final")

    m.connect(ini, validate)
    m.connect(validate, decision)
    m.connect(decision, approve, guard="approved")
    m.connect(decision, reject, guard="rejected")
    m.connect(approve, merge)
    m.connect(reject, merge)
    m.connect(merge, fork)
    m.connect(fork, log_it)
    m.connect(fork, notify)
    m.connect(log_it, join)
    m.connect(notify, join)
    m.connect(join, final)
    return m


def _exec_model(source: str) -> ActivityModel:
    namespace: dict = {}
    exec(source, namespace)
    candidate = namespace.get("activity")
    if isinstance(candidate, ActivityModel):
        return candidate
    for value in namespace.values():
        if isinstance(value, ActivityModel):
            return value
    raise AssertionError("No ActivityModel in namespace")


def _type_counts(model: ActivityModel) -> dict:
    counts: dict = {}
    for n in model.nodes:
        counts[type(n).__name__] = counts.get(type(n).__name__, 0) + 1
    return counts


def test_generated_code_execs_back():
    """The generated code reconstructs a model with the same node/edge shape."""
    model = _sample_model()
    rebuilt = _exec_model(activity_model_to_code(model))
    assert _type_counts(rebuilt) == _type_counts(model)
    assert len(rebuilt.edges) == len(model.edges)


def test_node_types_preserved():
    """Each concrete node type survives the exec round-trip."""
    rebuilt = _exec_model(activity_model_to_code(_sample_model()))
    present = {type(n) for n in rebuilt.nodes}
    for cls in (InitialNode, ActivityFinalNode, OpaqueAction,
                DecisionNode, MergeNode, ForkNode, JoinNode):
        assert cls in present


def test_guards_preserved():
    """Decision-branch guards survive the exec round-trip."""
    rebuilt = _exec_model(activity_model_to_code(_sample_model()))
    guards = {e.guard.body for e in rebuilt.edges if e.guard is not None}
    assert guards == {"approved", "rejected"}


def test_reconstructed_model_validates():
    """The rebuilt model passes the metamodel's own validate()."""
    rebuilt = _exec_model(activity_model_to_code(_sample_model()))
    result = rebuilt.validate(raise_exception=False)
    assert result["success"], result["errors"]


def test_output_is_deterministic():
    """Two builds of the same model produce identical source."""
    model = _sample_model()
    assert activity_model_to_code(model) == activity_model_to_code(model)


def test_no_binding_emitted():
    """Phase-1 scope: the builder never emits class-binding references."""
    source = activity_model_to_code(_sample_model())
    assert "ref_class" not in source
    assert "ref_method" not in source
    assert "ref_property" not in source


def test_non_identifier_and_colliding_names_exec():
    """Metamodel-legal but non-identifier / colliding node names still exec.

    ``NamedElement`` allows names like ``'1st'`` (leading digit); a naive
    ``{name}_node`` variable would be a SyntaxError, and two names that sanitize
    to the same stem would shadow each other. The var dispenser must prevent both.
    """
    m = ActivityModel(name="EdgeNames")
    start = m.new_initial("start")
    a = m.new_action("1st")   # sanitizes to stem 'st'
    b = m.new_action("st")    # collides with the sanitized stem of '1st'
    done = m.new_activity_final("done")
    m.connect(start, a)
    m.connect(a, b)
    m.connect(b, done)

    rebuilt = _exec_model(activity_model_to_code(m))  # must not raise SyntaxError/NameError
    assert {n.name for n in rebuilt.nodes} == {"start", "1st", "st", "done"}
    assert len(rebuilt.edges) == 3


def test_edge_weight_preserved():
    """A non-default edge weight survives the exec round-trip."""
    m = ActivityModel(name="Weighted")
    start = m.new_initial("start")
    a = m.new_action("a")
    done = m.new_activity_final("done")
    m.connect(start, a, weight=3)
    m.connect(a, done)

    rebuilt = _exec_model(activity_model_to_code(m))
    assert sorted(e.weight for e in rebuilt.edges) == [1, 3]


def test_empty_label_preserved():
    """An empty-string label (distinct from None) survives the exec round-trip."""
    m = ActivityModel(name="Labelled")
    start = m.new_initial("start")
    a = m.new_action("a")
    a.label = ""  # empty label, NOT None
    done = m.new_activity_final("done")
    m.connect(start, a)
    m.connect(a, done)

    rebuilt = _exec_model(activity_model_to_code(m))
    rebuilt_a = next(n for n in rebuilt.nodes if n.name == "a")
    assert rebuilt_a.label == ""


def test_writes_file(tmp_path):
    """When given a path, the builder writes the source to disk."""
    out = tmp_path / "activity.py"
    source = activity_model_to_code(_sample_model(), file_path=str(out))
    assert out.read_text(encoding="utf-8") == source
