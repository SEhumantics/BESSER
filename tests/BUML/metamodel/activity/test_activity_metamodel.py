"""Phase-0 tests for the self-contained activity-diagram metamodel.

Covers: construction/setter validation, the abstract-class guards, the
class-diagram binding (ref_class/ref_method/ref_property), the derived
incoming()/outgoing() topology, guard round-trip via source=, and the
validate() {success, errors, warnings} contract (E-series + W-series).
"""

import pytest

from besser.BUML.metamodel.structural import Class, Method, Property, Type
from besser.BUML.metamodel import activity as activity_module
from besser.BUML.metamodel.activity import (
    ActivityModel,
    ActivityNode,
    ActivityEdge,
    ControlNode,
    FinalNode,
    ExecutableNode,
    Action,
    OpaqueAction,
    InitialNode,
    ActivityFinalNode,
    FlowFinalNode,
    DecisionNode,
    MergeNode,
    ForkNode,
    JoinNode,
    ControlFlow,
    Condition,
    OpaqueBehavior,
)


# --------------------------------------------------------------------------- #
# Fixtures validate clean
# --------------------------------------------------------------------------- #

def test_linear_validates_clean(linear_activity_model):
    result = linear_activity_model.validate(raise_exception=False)
    assert result["success"] is True
    assert result["errors"] == []


def test_decision_validates_clean(decision_activity_model):
    result = decision_activity_model.validate(raise_exception=False)
    assert result["success"] is True, result["errors"]
    assert result["errors"] == []


def test_concurrent_validates_clean(concurrent_activity_model):
    result = concurrent_activity_model.validate(raise_exception=False)
    assert result["success"] is True, result["errors"]
    assert result["errors"] == []


def test_validate_returns_contract_keys(linear_activity_model):
    result = linear_activity_model.validate(raise_exception=False)
    assert set(result.keys()) == {"success", "errors", "warnings"}
    assert isinstance(result["errors"], list)
    assert isinstance(result["warnings"], list)


# --------------------------------------------------------------------------- #
# Self-containment: activity defines its own Condition (no state_machine reuse)
# --------------------------------------------------------------------------- #

def test_activity_is_self_contained():
    from besser.BUML.metamodel.state_machine import Condition as SMCondition
    assert Condition is not SMCondition


def test_condition_source_round_trip():
    guard = Condition("is_ok", source="def is_ok(params):\n    return True")
    assert "return True" in guard.code
    assert guard.type.name == "bool"


def test_condition_has_no_session_param():
    guard = Condition("g", source="def g(params):\n    return True")
    param_names = {p.name for p in guard.parameters}
    assert param_names == {"params"}  # activities have no runtime Session


# --------------------------------------------------------------------------- #
# Abstract-class guards
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("abstract_cls", [ActivityNode, ControlNode, FinalNode, ExecutableNode, Action])
def test_abstract_nodes_cannot_be_instantiated(abstract_cls):
    with pytest.raises(TypeError):
        abstract_cls("x")


def test_activity_edge_is_abstract():
    n1 = OpaqueAction("a")
    n2 = OpaqueAction("b")
    with pytest.raises(TypeError):
        ActivityEdge(source=n1, target=n2)


def test_concrete_nodes_instantiate():
    for cls in (InitialNode, ActivityFinalNode, FlowFinalNode, MergeNode, ForkNode):
        assert isinstance(cls("n"), ActivityNode)
    assert isinstance(OpaqueAction("a"), Action)
    assert isinstance(DecisionNode("d"), ControlNode)
    assert isinstance(JoinNode("j"), ControlNode)


# --------------------------------------------------------------------------- #
# Name validation (identifier-safe) + display label
# --------------------------------------------------------------------------- #

def test_node_name_rejects_spaces():
    with pytest.raises(ValueError):
        OpaqueAction("Do Payment")


def test_node_name_rejects_hyphens():
    with pytest.raises(ValueError):
        OpaqueAction("do-payment")


def test_label_is_free_form():
    a = OpaqueAction("do_payment", label="Do Payment!")
    assert a.label == "Do Payment!"
    assert a.name == "do_payment"


# --------------------------------------------------------------------------- #
# Class-diagram binding (nullable, type-checked)
# --------------------------------------------------------------------------- #

def test_ref_class_accepts_class_and_none():
    entity = Class(name="Entity")
    a = OpaqueAction("do_task", ref_class=entity)
    assert a.ref_class is entity
    b = OpaqueAction("noop")
    assert b.ref_class is None


def test_ref_class_rejects_non_class():
    with pytest.raises(TypeError):
        OpaqueAction("bad", ref_class="Entity")


def test_ref_method_and_property_type_checked():
    entity = Class(name="Entity")
    m = Method(name="run")
    p = Property(name="value", type=Type("int"))
    a = OpaqueAction("act", ref_class=entity, ref_method=m, ref_property=p)
    assert a.ref_method is m and a.ref_property is p
    with pytest.raises(TypeError):
        OpaqueAction("bad", ref_method="submit")


# --------------------------------------------------------------------------- #
# Body seam
# --------------------------------------------------------------------------- #

def test_action_body_is_opaque_behavior():
    body = OpaqueBehavior("compute", source="def compute(params):\n    params['x'] = 1")
    a = OpaqueAction("do", body=body)
    assert a.body is body
    assert "params['x'] = 1" in a.body.code


def test_body_rejects_wrong_type():
    with pytest.raises(TypeError):
        OpaqueAction("do", body="not a behavior")


# --------------------------------------------------------------------------- #
# Edge construction, guards, weight
# --------------------------------------------------------------------------- #

def test_connect_creates_named_control_flow():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    e = m.connect(i, a)
    assert isinstance(e, ControlFlow)
    assert e.source is i and e.target is a
    assert e.name.startswith("e_")


def test_guard_must_be_condition():
    m = ActivityModel("M")
    d = m.new_decision("d")
    a = m.new_action("a")
    with pytest.raises(TypeError):
        m.connect(d, a, guard="return True")


def test_weight_star_is_unlimited():
    from besser.BUML.metamodel.structural import UNLIMITED_MAX_MULTIPLICITY
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    e = m.connect(i, a, weight="*")
    assert e.weight == UNLIMITED_MAX_MULTIPLICITY


def test_weight_below_one_rejected():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    with pytest.raises(ValueError):
        m.connect(i, a, weight=0)


def test_edge_endpoint_must_be_node():
    with pytest.raises(TypeError):
        ControlFlow(source="x", target=OpaqueAction("a"))


# --------------------------------------------------------------------------- #
# Derived topology + uniqueness
# --------------------------------------------------------------------------- #

def test_incoming_outgoing_derived(linear_activity_model):
    a = linear_activity_model.get_node_by_name("do_work")
    assert len(a.incoming()) == 1
    assert len(a.outgoing()) == 1
    initial = linear_activity_model.initial_nodes()[0]
    assert initial.incoming() == set()


def test_duplicate_node_name_rejected():
    m = ActivityModel("M")
    m.new_action("dup")
    with pytest.raises(ValueError):
        m.new_action("dup")


def test_elements_aggregate(linear_activity_model):
    m = linear_activity_model
    assert m.elements == (m.nodes | m.edges)


# --------------------------------------------------------------------------- #
# validate() error rules
# --------------------------------------------------------------------------- #

def test_missing_initial_is_error():
    m = ActivityModel("M")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("InitialNode" in e for e in result["errors"])


def test_final_with_outgoing_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    f = m.new_activity_final("f")
    a = m.new_action("a")
    m.connect(i, f)
    m.connect(f, a)  # illegal outgoing from final
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("Final" in e for e in result["errors"])


def test_decision_unguarded_branch_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    d = m.new_decision("d")
    b = m.new_action("b")
    c = m.new_action("c")
    f = m.new_activity_final("f")
    m.connect(i, d)
    m.connect(d, b, guard=Condition("g", source="def g(params):\n    return True"))
    m.connect(d, c)  # unguarded, not default -> E5
    m.connect(b, f)
    m.connect(c, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("guard" in e.lower() or "default" in e.lower() for e in result["errors"])


def test_decision_branch_into_merge_is_clean():
    """A decision branch flowing straight into a merge carries the decision's
    guard on the merge's *incoming* edge — this is legal; only the merge's own
    outgoing edge must be unguarded."""
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("step")
    d = m.new_decision("d")
    handle = m.new_action("handle")
    mg = m.new_merge("merge")
    f = m.new_activity_final("f")
    m.connect(i, a)
    m.connect(a, d)
    m.connect(d, handle, guard=Condition("cond_a", source="def cond_a(params):\n    return True"))
    # a genuinely guarded (non-default) decision branch straight into the merge:
    m.connect(d, mg, guard=Condition("cond_b", source="def cond_b(params):\n    return False"))
    m.connect(handle, mg)
    m.connect(mg, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is True, result["errors"]


def test_default_branch_with_guard_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    d = m.new_decision("d")
    b = m.new_action("b")
    c = m.new_action("c")
    f = m.new_activity_final("f")
    m.connect(i, d)
    m.connect(d, b, guard=Condition("g", source="def g(params):\n    return True"))
    m.connect(d, c, guard=Condition("h", source="def h(params):\n    return False"), is_default=True)
    m.connect(b, f)
    m.connect(c, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("default" in e.lower() for e in result["errors"])


def test_guard_on_non_decision_edge_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, a)
    m.connect(a, f, guard=Condition("g", source="def g(params):\n    return True"))
    result = m.validate(raise_exception=False)
    assert result["success"] is False


def test_initial_with_incoming_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, a)
    m.connect(a, i)  # incoming to initial -> E2
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False


def test_validate_raises_when_requested():
    m = ActivityModel("M")  # empty -> at least the missing-initial error
    with pytest.raises(ValueError):
        m.validate(raise_exception=True)


# --------------------------------------------------------------------------- #
# validate() warnings
# --------------------------------------------------------------------------- #

def test_multiple_initials_is_warning_not_error():
    m = ActivityModel("M")
    i1 = m.new_initial("s1")
    i2 = m.new_initial("s2")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i1, a)
    m.connect(i2, a)
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is True  # permissive: multiple initials is a warning
    assert len(result["warnings"]) >= 1


def test_unreachable_node_is_warning():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    orphan = m.new_action("orphan")
    stub = m.new_activity_final("orphan_end")
    m.connect(i, a)
    m.connect(a, f)
    m.connect(orphan, stub)  # orphan not reachable from initial
    result = m.validate(raise_exception=False)
    assert any("unreachable" in w.lower() for w in result["warnings"])


# --------------------------------------------------------------------------- #
# Model-integrity guards (fail-fast) + more validate() negative branches
# --------------------------------------------------------------------------- #

def test_cross_model_reparenting_rejected():
    """A node owned by one activity cannot be added to another (would corrupt the
    first model's derived incoming()/outgoing())."""
    a_model = ActivityModel("A")
    node = a_model.new_action("shared")
    b_model = ActivityModel("B")
    with pytest.raises(ValueError):
        b_model.add_node(node)


def test_connect_rejects_foreign_endpoint():
    m = ActivityModel("M")
    i = m.new_initial("s")
    stray = OpaqueAction("stray")  # never added to m
    with pytest.raises(ValueError):
        m.connect(i, stray)


def test_edge_with_foreign_endpoint_is_error_via_add_edge():
    """add_edge stays permissive (low-level), so the E10 dangling-edge rule is reachable."""
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    stray = OpaqueAction("stray")  # not a node of m
    m.connect(i, a)
    m.add_edge(ControlFlow(source=a, target=stray, name="e_x"))
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("not part of" in e.lower() for e in result["errors"])


def test_is_default_on_non_decision_edge_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, a)
    m.connect(a, f, is_default=True)  # is_default only valid on a DecisionNode out-branch
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("default" in e.lower() for e in result["errors"])


def test_fork_guarded_branch_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    fk = m.new_fork("fk")
    a = m.new_action("a")
    b = m.new_action("b")
    f = m.new_activity_final("f")
    m.connect(i, fk)
    m.connect(fk, a, guard=Condition("g", source="def g(params):\n    return True"))
    m.connect(fk, b)
    m.connect(a, f)
    m.connect(b, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("fork" in e.lower() for e in result["errors"])


def test_join_single_incoming_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    jn = m.new_join("jn")
    f = m.new_activity_final("f")
    m.connect(i, a)
    m.connect(a, jn)  # only 1 incoming to the join
    m.connect(jn, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("join" in e.lower() for e in result["errors"])


def test_merge_guarded_outgoing_is_error():
    m = ActivityModel("M")
    i1 = m.new_initial("s1")
    i2 = m.new_initial("s2")
    mg = m.new_merge("mg")
    f = m.new_activity_final("f")
    m.connect(i1, mg)
    m.connect(i2, mg)
    m.connect(mg, f, guard=Condition("g", source="def g(params):\n    return True"))
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("merge" in e.lower() for e in result["errors"])


# --------------------------------------------------------------------------- #
# Extension surface (freezes the subclassing contract — no base change needed)
# --------------------------------------------------------------------------- #

def test_extension_surface_is_stable():
    """A specialized profile must be able to subclass the base nodes/container, add
    its own payload, and drive the model API + validate() with no change to activity.py."""
    class ExtAction(OpaqueAction):
        def __init__(self, name, extra=None, **kw):
            super().__init__(name, **kw)
            self.extra = extra

    class ExtDecision(DecisionNode):
        pass

    class ExtModel(ActivityModel):
        pass

    entity = Class(name="Entity")
    am = ExtModel("ext")
    i = am.new_initial("start")
    act = am.add_node(ExtAction("do", extra="payload", ref_class=entity))
    dec = am.add_node(ExtDecision("decide"))
    g = am.new_action("g")
    f = am.new_activity_final("end")
    am.connect(i, act)
    am.connect(act, dec)
    am.connect(dec, g, guard=Condition("c", source="def c(params):\n    return True"))
    am.connect(dec, f, is_default=True)
    am.connect(g, f)
    result = am.validate(raise_exception=False)
    assert result["success"] is True, result["errors"]
    # subclass payload + inherited base binding both present:
    assert act.extra == "payload"
    assert act.ref_class is entity
    # validate() dispatches by isinstance, so the subclass is treated as a DecisionNode:
    assert isinstance(dec, DecisionNode)
