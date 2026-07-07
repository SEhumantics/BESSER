"""Tests for the general-purpose, class-bindable activity-diagram metamodel.

Covers: construction/setter validation, the abstract-class guards, stringly
OpaqueExpression guards/bodies, the class-diagram binding on executable nodes
(and its absence on control nodes), the activity-level ``context`` owning class,
the ``layout`` interchange passthrough, derived incoming()/outgoing() topology,
and the validate() {success, errors, warnings} contract (E-series + W-series).
"""

import datetime

import pytest

from besser.BUML.metamodel.structural import Class, Method, Property, Type
from besser.BUML.metamodel.activity import (
    ActivityModel,
    ActivityElement,
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
    OpaqueExpression,
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
# Self-containment: no state_machine coupling
# --------------------------------------------------------------------------- #

def test_activity_is_self_contained():
    """The package must never IMPORT state_machine (docstrings may still mention it)."""
    import ast
    import besser.BUML.metamodel.activity as activity_pkg
    tree = ast.parse(open(activity_pkg.activity.__file__, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported = (getattr(node, "module", "") or "") + " " + " ".join(a.name for a in node.names)
            assert "state_machine" not in imported


# --------------------------------------------------------------------------- #
# OpaqueExpression (stringly guards/bodies)
# --------------------------------------------------------------------------- #

def test_opaque_expression_body_and_language():
    e = OpaqueExpression(body="self.isPaid", language="OCL")
    assert e.body == "self.isPaid"
    assert e.language == "OCL"


def test_opaque_expression_defaults_untagged():
    e = OpaqueExpression(body="payment approved")
    assert e.language is None


def test_opaque_expression_equality_and_hash():
    a = OpaqueExpression("x", "OCL")
    b = OpaqueExpression("x", "OCL")
    assert a == b
    assert hash(a) == hash(b)
    assert a != OpaqueExpression("x")


def test_opaque_expression_rejects_non_string_body():
    with pytest.raises(TypeError):
        OpaqueExpression(body=123)


def test_guard_coerces_plain_string():
    m = ActivityModel("M")
    d = m.new_decision("d")
    a = m.new_action("a")
    e = m.connect(d, a, guard="approved", is_default=False)
    assert isinstance(e.guard, OpaqueExpression)
    assert e.guard.body == "approved"
    assert e.guard.language is None


def test_guard_accepts_opaque_expression():
    m = ActivityModel("M")
    d = m.new_decision("d")
    a = m.new_action("a")
    e = m.connect(d, a, guard=OpaqueExpression("self.ok", "OCL"))
    assert e.guard.language == "OCL"


def test_guard_rejects_wrong_type():
    m = ActivityModel("M")
    d = m.new_decision("d")
    a = m.new_action("a")
    with pytest.raises(TypeError):
        m.connect(d, a, guard=123)


# --------------------------------------------------------------------------- #
# Abstract-class guards
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("abstract_cls", [ActivityElement, ActivityNode, ControlNode,
                                          FinalNode, ExecutableNode, Action])
def test_abstract_classes_cannot_be_instantiated(abstract_cls):
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
# Class-diagram binding lives on ExecutableNode (not on control nodes)
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


def test_ref_property_rejects_non_property():
    with pytest.raises(TypeError):
        OpaqueAction("bad", ref_property="value")


def test_control_nodes_have_no_binding():
    """Binding lives on ExecutableNode; control-node factories reject ref_* kwargs."""
    entity = Class(name="Entity")
    for cls in (InitialNode, ActivityFinalNode, FlowFinalNode, DecisionNode, MergeNode, ForkNode, JoinNode):
        with pytest.raises(TypeError):
            cls("n", ref_class=entity)
        # and a plain control node exposes no ref_class attribute
        assert not hasattr(cls("n"), "ref_class")


# --------------------------------------------------------------------------- #
# Body seam (stringly)
# --------------------------------------------------------------------------- #

def test_action_body_accepts_expression_and_string():
    a = OpaqueAction("do", body=OpaqueExpression("params['x'] = 1", "Python"))
    assert a.body.body == "params['x'] = 1"
    assert a.body.language == "Python"
    b = OpaqueAction("do2", body="process the order")
    assert isinstance(b.body, OpaqueExpression)
    assert b.body.body == "process the order"


def test_body_rejects_wrong_type():
    with pytest.raises(TypeError):
        OpaqueAction("do", body=123)


# --------------------------------------------------------------------------- #
# Activity owning-class context
# --------------------------------------------------------------------------- #

def test_context_accepts_class_and_none():
    entity = Class(name="Order")
    m = ActivityModel("bound", context=entity)
    assert m.context is entity
    m2 = ActivityModel("unbound")
    assert m2.context is None


def test_context_rejects_non_class():
    with pytest.raises(TypeError):
        ActivityModel("bad", context="Order")


# --------------------------------------------------------------------------- #
# layout interchange passthrough
# --------------------------------------------------------------------------- #

def test_layout_passthrough_on_node_and_edge():
    a = OpaqueAction("a", layout={"x": 10, "y": 20})
    assert a.layout == {"x": 10, "y": 20}
    m = ActivityModel("M")
    i = m.new_initial("s")
    m.add_node(a)
    e = m.connect(i, a, name="e_x")
    e.layout = {"points": [[0, 0], [1, 1]]}
    assert e.layout["points"] == [[0, 0], [1, 1]]


def test_layout_rejects_non_dict():
    with pytest.raises(TypeError):
        OpaqueAction("a", layout="not a dict")


def test_layout_is_ignored_by_validate(linear_activity_model):
    for n in linear_activity_model.nodes:
        n.layout = {"x": 1}
    result = linear_activity_model.validate(raise_exception=False)
    assert result["success"] is True


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
    m.connect(d, b, guard="cond")
    m.connect(d, c)  # unguarded, not default -> E5
    m.connect(b, f)
    m.connect(c, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("guard" in e.lower() or "default" in e.lower() for e in result["errors"])


def test_decision_branch_into_merge_is_clean():
    """A decision branch flowing straight into a merge carries the decision's
    guard on the merge's *incoming* edge -- this is legal; only the merge's own
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
    m.connect(d, handle, guard="cond_a")
    # a genuinely guarded (non-default) decision branch straight into the merge:
    m.connect(d, mg, guard="cond_b")
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
    m.connect(d, b, guard="cond")
    m.connect(d, c, guard="other", is_default=True)
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
    m.connect(a, f, guard="cond")
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


def test_connect_rejects_foreign_source():
    """Mirror of the target-side guard: connect() also rejects a foreign source."""
    m = ActivityModel("M")
    a = m.new_action("a")
    stray = OpaqueAction("stray")  # never added to m
    with pytest.raises(ValueError):
        m.connect(stray, a)


def test_edge_with_foreign_source_is_error_via_add_edge():
    """Mirror of the target-side E10 test: a foreign SOURCE is also flagged by validate()."""
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    stray = OpaqueAction("stray")  # not a node of m
    m.connect(i, a)
    m.add_edge(ControlFlow(source=stray, target=a, name="e_src"))
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
    m.connect(fk, a, guard="cond")
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
    m.connect(mg, f, guard="cond")
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("merge" in e.lower() for e in result["errors"])


# --------------------------------------------------------------------------- #
# Extension surface (freezes the subclassing contract -- no base change needed)
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
    am = ExtModel("ext", context=entity)
    i = am.new_initial("start")
    act = am.add_node(ExtAction("do", extra="payload", ref_class=entity))
    dec = am.add_node(ExtDecision("decide"))
    g = am.new_action("g")
    f = am.new_activity_final("end")
    am.connect(i, act)
    am.connect(act, dec)
    am.connect(dec, g, guard="cond")
    am.connect(dec, f, is_default=True)
    am.connect(g, f)
    result = am.validate(raise_exception=False)
    assert result["success"] is True, result["errors"]
    # subclass payload + inherited base binding both present:
    assert act.extra == "payload"
    assert act.ref_class is entity
    # validate() dispatches by isinstance, so the subclass is treated as a DecisionNode:
    assert isinstance(dec, DecisionNode)
    # the activity carries its owning class context:
    assert am.context is entity


# --------------------------------------------------------------------------- #
# FlowFinalNode (end-to-end)
# --------------------------------------------------------------------------- #

def test_flow_final_happy_path_validates_clean():
    m = ActivityModel("M")
    i = m.new_initial("s")
    fk = m.new_fork("split")
    a1 = m.new_action("a1")
    a2 = m.new_action("a2")
    ff = m.new_flow_final("consume")      # one branch consumes its token
    end = m.new_activity_final("end")     # the other ends the activity
    assert isinstance(ff, FlowFinalNode)
    m.connect(i, fk)
    m.connect(fk, a1)
    m.connect(fk, a2)
    m.connect(a1, ff)
    m.connect(a2, end)
    result = m.validate(raise_exception=False)
    assert result["success"] is True, result["errors"]


def test_flow_final_with_outgoing_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    ff = m.new_flow_final("ff")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, ff)
    m.connect(ff, a)  # illegal outgoing from a final node -> E4
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("Final" in e for e in result["errors"])


# --------------------------------------------------------------------------- #
# weight rejection branches
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad_weight", [True, False, 1.5, "abc", "5"])
def test_weight_rejects_non_int(bad_weight):
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    with pytest.raises(ValueError):
        m.connect(i, a, weight=bad_weight)


# --------------------------------------------------------------------------- #
# Control-node arity branches (regression guards for the E5-E8 comparisons)
# --------------------------------------------------------------------------- #

def test_decision_single_outgoing_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    d = m.new_decision("d")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, d)
    m.connect(d, a, guard="g")  # only 1 outgoing -> E5
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("DecisionNode" in e and "2 outgoing" in e for e in result["errors"])


def test_decision_two_defaults_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    d = m.new_decision("d")
    a = m.new_action("a")
    b = m.new_action("b")
    f = m.new_activity_final("f")
    m.connect(i, d)
    m.connect(d, a, is_default=True)
    m.connect(d, b, is_default=True)  # two defaults -> E5
    m.connect(a, f)
    m.connect(b, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("more than one default" in e for e in result["errors"])


def test_fork_single_outgoing_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    fk = m.new_fork("fk")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, fk)
    m.connect(fk, a)  # only 1 outgoing -> E6
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("ForkNode" in e and "2 outgoing" in e for e in result["errors"])


def test_join_multiple_outgoing_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    b = m.new_action("b")
    jn = m.new_join("jn")
    x = m.new_action("x")
    y = m.new_action("y")
    f1 = m.new_activity_final("f1")
    f2 = m.new_activity_final("f2")
    m.connect(i, a)
    m.connect(a, b)
    m.connect(a, jn)
    m.connect(b, jn)   # 2 incoming (ok)
    m.connect(jn, x)   # 2 outgoing -> E7
    m.connect(jn, y)
    m.connect(x, f1)
    m.connect(y, f2)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("JoinNode" in e and "1 outgoing" in e for e in result["errors"])


def test_merge_single_incoming_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    mg = m.new_merge("mg")
    f = m.new_activity_final("f")
    m.connect(i, mg)  # only 1 incoming -> E8
    m.connect(mg, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("MergeNode" in e and "2 incoming" in e for e in result["errors"])


def test_decision_multiple_incoming_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    fk = m.new_fork("fk")
    a = m.new_action("a")
    b = m.new_action("b")
    d = m.new_decision("d")
    x = m.new_action("x")
    f = m.new_activity_final("f")
    m.connect(i, fk)
    m.connect(fk, a)
    m.connect(fk, b)
    m.connect(a, d)
    m.connect(b, d)   # decision has 2 incoming -> E5
    m.connect(d, x, guard="g")
    m.connect(d, f, is_default=True)
    m.connect(x, f)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("DecisionNode" in e and "1 incoming" in e for e in result["errors"])


def test_fork_multiple_incoming_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    b = m.new_action("b")
    fk = m.new_fork("fk")
    x = m.new_action("x")
    y = m.new_action("y")
    f1 = m.new_activity_final("f1")
    f2 = m.new_activity_final("f2")
    m.connect(i, a)
    m.connect(a, b)
    m.connect(a, fk)
    m.connect(b, fk)   # fork has 2 incoming -> E6
    m.connect(fk, x)
    m.connect(fk, y)
    m.connect(x, f1)
    m.connect(y, f2)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("ForkNode" in e and "1 incoming" in e for e in result["errors"])


def test_merge_multiple_outgoing_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    fk = m.new_fork("fk")
    a = m.new_action("a")
    b = m.new_action("b")
    mg = m.new_merge("mg")
    x = m.new_action("x")
    y = m.new_action("y")
    f1 = m.new_activity_final("f1")
    f2 = m.new_activity_final("f2")
    m.connect(i, fk)
    m.connect(fk, a)
    m.connect(fk, b)
    m.connect(a, mg)
    m.connect(b, mg)   # merge has 2 incoming (ok)
    m.connect(mg, x)   # 2 outgoing -> E8
    m.connect(mg, y)
    m.connect(x, f1)
    m.connect(y, f2)
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("MergeNode" in e and "1 outgoing" in e for e in result["errors"])


# --------------------------------------------------------------------------- #
# Isolated rule assertions: E3, W2, E14
# --------------------------------------------------------------------------- #

def test_initial_without_outgoing_is_error():
    m = ActivityModel("M")
    m.new_initial("s")            # present but dangling -> E3
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(a, f)
    result = m.validate(raise_exception=False)
    assert any("at least one outgoing edge" in e for e in result["errors"])


def test_no_final_node_is_warning():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    m.connect(i, a)              # no final node anywhere -> W2
    result = m.validate(raise_exception=False)
    assert any("no final node" in w.lower() for w in result["warnings"])


def test_action_without_edges_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    f = m.new_activity_final("f")
    m.new_action("lonely")       # no incoming/outgoing -> E14
    m.connect(i, f)
    result = m.validate(raise_exception=False)
    assert any("no incoming edge" in e.lower() or "no outgoing edge" in e.lower()
               for e in result["errors"])


# --------------------------------------------------------------------------- #
# Bulk collection setters + foreign-ownership guards + fail-fast type guards
# --------------------------------------------------------------------------- #

def test_bulk_nodes_duplicate_name_rejected():
    with pytest.raises(ValueError):
        ActivityModel("M", nodes={InitialNode("dup"), OpaqueAction("dup")})


def test_bulk_nodes_foreign_rejected():
    a_model = ActivityModel("A")
    node = a_model.new_action("shared")
    with pytest.raises(ValueError):
        ActivityModel("B", nodes={node})


def test_bulk_nodes_wrong_type_rejected():
    with pytest.raises(TypeError):
        ActivityModel("M", nodes={"not a node"})


def test_edges_setter_wrong_type_rejected():
    m = ActivityModel("M")
    with pytest.raises(TypeError):
        m.edges = {"not an edge"}


def test_edge_foreign_ownership_rejected():
    """An edge owned by one activity cannot be re-parented into another (the fix
    mirroring the nodes-side guard)."""
    a_model = ActivityModel("A")
    i = a_model.new_initial("s")
    a = a_model.new_action("a")
    e = a_model.connect(i, a)  # e.activity is a_model
    b_model = ActivityModel("B")
    with pytest.raises(ValueError):
        b_model.add_edge(e)
    with pytest.raises(ValueError):
        b_model.edges = {e}


def test_add_node_and_add_edge_type_guards():
    m = ActivityModel("M")
    with pytest.raises(TypeError):
        m.add_node("not a node")
    with pytest.raises(TypeError):
        m.add_edge("not an edge")


def test_bulk_nodes_and_edges_back_link():
    """The bulk-setter happy path: passing non-empty nodes=/edges= sets back-links
    each element to the model and keeps elements == nodes | edges."""
    i = InitialNode("s")
    a = OpaqueAction("a")
    m = ActivityModel("M", nodes={i, a})
    assert i.activity is m and a.activity is m
    e = ControlFlow(source=i, target=a, name="e_1")
    m.edges = {e}
    assert e.activity is m
    assert m.elements == m.nodes | m.edges


# --------------------------------------------------------------------------- #
# is_default validation, missing endpoint, expression + detached paths
# --------------------------------------------------------------------------- #

def test_is_default_rejects_non_bool():
    m = ActivityModel("M")
    d = m.new_decision("d")
    a = m.new_action("a")
    with pytest.raises(TypeError):
        m.connect(d, a, is_default="yes")


def test_missing_endpoint_is_error():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    f = m.new_activity_final("f")
    m.connect(i, a)
    m.connect(a, f)
    m.add_edge(ControlFlow(source=None, target=a, name="dangling"))  # None source -> E10
    result = m.validate(raise_exception=False)
    assert result["success"] is False
    assert any("missing endpoint" in e.lower() for e in result["errors"])


def test_opaque_expression_language_rejects_non_string():
    with pytest.raises(TypeError):
        OpaqueExpression(body="x", language=123)


def test_incoming_outgoing_empty_when_detached():
    a = OpaqueAction("floating")  # never added to a model -> activity is None
    assert a.incoming() == set()
    assert a.outgoing() == set()


def test_edge_visibility_defaults_public():
    m = ActivityModel("M")
    i = m.new_initial("s")
    a = m.new_action("a")
    e = m.connect(i, a)
    assert e.visibility == "public"


def test_timestamp_passthrough_on_node_and_edge():
    """Element bases forward ``timestamp`` to NamedElement (parity with bpmn.BPMNElement)."""
    ts = datetime.datetime(2020, 1, 1)
    i = InitialNode("s")
    a = OpaqueAction("a", timestamp=ts)
    e = ControlFlow(source=i, target=a, name="e_1", timestamp=ts)
    assert a.timestamp == ts
    assert e.timestamp == ts


def test_duplicate_name_via_post_insert_rename_is_error():
    """Uniqueness is enforced at insertion; a post-insert rename can still collide,
    which validate() catches (E13) — so E13 is reachable, not dead code."""
    m = ActivityModel("M")
    m.new_action("a")
    b = m.new_action("b")
    b.name = "a"  # bypasses insertion-time uniqueness
    result = m.validate(raise_exception=False)
    assert any("Duplicate node names" in e for e in result["errors"])
