"""Tests for the AGL BPMN sibling extension (``besser.BUML.metamodel.bpmn.agl``).

AGL (Activity Graph Language, Dang/Le/Le IST 2023) realized as a pure-addition sibling
of the BPMN base, mirroring ``bpmn/agentic.py``. Groups:

    1. ModuleAct -- construction + the canonical core-action state table (IST Table 1).
    2. AGLTask -- action-node binding + act_sequence.
    3. AGLGateway -- control-node binding, gateway-type restriction, control_role.
    4. AGLModel -- context, start_nodes, and validate() rules A1-A5.
    5. Base-BPMN rules still fire through AGLModel.validate().
    6. A faithful AGL realization (CourseMan enrollment) validates cleanly.

The base ``bpmn.py`` stays domain-neutral; the domain realization lives here in the tests.
"""

import pytest

from besser.BUML.metamodel.bpmn.bpmn import (
    GatewayType, Process, SequenceFlow, Task,
)
from besser.BUML.metamodel.bpmn.agl import (
    ActName, State, ModuleAct, AGLTask, AGLGateway, AGLModel, _CORE_ACTION_STATES,
)
from besser.BUML.metamodel.structural import Class, Method


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _seq(*acts):
    """A valid ASE (each action's post-states subset the next's pre-states)."""
    return list(acts)


@pytest.fixture
def valid_open_new():
    """A two-step valid ASE: open -> newObject (open.post={Opened} ⊆ newObject.pre)."""
    return [ModuleAct.core(ActName.OPEN), ModuleAct.core(ActName.NEW_OBJECT)]


@pytest.fixture
def enrollment_model():
    """A faithful (small) AGL realization: the CourseMan enrollment activity graph.

    Student action node -> DHelpOrSClass decision -> {HelpRequest, SClassRegistration}.
    Mirrors IST-2023 Fig 11 / Table 2. Validates cleanly.
    """
    student_cls = Class(name="Student")
    data_controller = Class(name="DataController")
    decision_cls = Class(name="DHelpOrSClass", is_abstract=True)
    evaluate = Method(name="evaluate", is_abstract=True, owner=decision_cls)
    help_cls = Class(name="HelpRequest")
    reg_cls = Class(name="SClassRegistration")

    student = AGLTask("MStudent", ref_class=student_cls, service_class=data_controller,
                      act_sequence=[ModuleAct.core(ActName.OPEN)])
    decision = AGLGateway("MDHelpOrSClass", gateway_type=GatewayType.EXCLUSIVE,
                          ref_class=decision_cls, logic_method=evaluate)
    help_req = AGLTask("MHelpRequest", ref_class=help_cls, service_class=data_controller,
                       act_sequence=[ModuleAct.core(ActName.OPEN)])
    reg = AGLTask("MSClassRegistration", ref_class=reg_cls, service_class=data_controller,
                  act_sequence=[ModuleAct.core(ActName.OPEN)])
    process = Process("enrollment")
    for node in (student, decision, help_req, reg):
        process.add_flow_node(node)
    for flow in (SequenceFlow(student, decision), SequenceFlow(decision, help_req),
                 SequenceFlow(decision, reg)):
        process.add_sequence_flow(flow)
    model = AGLModel("EnrollmentAGC", context=Class(name="EnrollmentActivity"),
                     processes={process})
    return model


# ---------------------------------------------------------------------------
# Group 1 -- ModuleAct
# ---------------------------------------------------------------------------

def test_module_act_core_matches_table_1():
    """Every core action's canonical pre/post states come straight from IST-2023 Table 1."""
    expected = {
        ActName.OPEN: ({State.INIT}, {State.OPENED}),
        ActName.NEW_OBJECT: (
            {State.OPENED, State.CREATED, State.UPDATED, State.RESET, State.CANCELLED},
            {State.NEW_OBJECT},
        ),
        ActName.RESET: ({State.EDITING}, {State.RESET}),
        ActName.CANCEL: (
            {State.NEW_OBJECT, State.EDITING, State.OBJ_IS_NOT_PRESENT},
            {State.CANCELLED},
        ),
    }
    for act_name, (pre, post) in expected.items():
        m = ModuleAct.core(act_name)
        assert m.pre_states == pre, act_name
        assert m.post_states == post, act_name


def test_module_act_core_covers_all_eight_actions():
    """All eight core actions have a canonical entry and build without error."""
    assert len(_CORE_ACTION_STATES) == 8
    for act_name in ActName:
        m = ModuleAct.core(act_name)
        assert m.act_name is act_name
        assert m.name == act_name.value


def test_module_act_core_rejects_non_actname():
    with pytest.raises(TypeError):
        ModuleAct.core("open")


def test_module_act_defaults_name_to_action_value():
    assert ModuleAct(ActName.OPEN).name == "open"
    assert ModuleAct(ActName.OPEN, name="custom").name == "custom"


def test_module_act_act_name_must_be_actname():
    with pytest.raises(TypeError):
        ModuleAct("open")


def test_module_act_states_must_be_state_instances():
    with pytest.raises(TypeError):
        ModuleAct(ActName.OPEN, pre_states={"Init"})
    with pytest.raises(TypeError):
        ModuleAct(ActName.OPEN, post_states={"Opened"})


def test_module_act_output_must_be_str_or_none():
    assert ModuleAct(ActName.OPEN, output=None).output is None
    assert ModuleAct(ActName.OPEN, output="view").output == "view"
    with pytest.raises(TypeError):
        ModuleAct(ActName.OPEN, output=123)


# ---------------------------------------------------------------------------
# Group 2 -- AGLTask
# ---------------------------------------------------------------------------

def test_agl_task_is_a_task():
    assert isinstance(AGLTask("x"), Task)


def test_agl_task_binding_defaults_none():
    t = AGLTask("x")
    assert t.ref_class is None
    assert t.service_class is None
    assert t.act_sequence == []


def test_agl_task_ref_class_type_checked():
    with pytest.raises(TypeError):
        AGLTask("x", ref_class="Student")
    with pytest.raises(TypeError):
        AGLTask("x", service_class=42)


def test_agl_task_act_sequence_must_be_list_of_module_acts():
    with pytest.raises(TypeError):
        AGLTask("x", act_sequence=ModuleAct.core(ActName.OPEN))  # not a list
    with pytest.raises(TypeError):
        AGLTask("x", act_sequence=[ModuleAct.core(ActName.OPEN), "nope"])


def test_agl_task_act_sequence_is_copied():
    """The setter stores a copy so external mutation of the passed list does not leak in."""
    src = [ModuleAct.core(ActName.OPEN)]
    t = AGLTask("x", ref_class=Class(name="C"), act_sequence=src)
    src.append(ModuleAct.core(ActName.CANCEL))
    assert len(t.act_sequence) == 1


# ---------------------------------------------------------------------------
# Group 3 -- AGLGateway
# ---------------------------------------------------------------------------

def test_agl_gateway_default_type_is_exclusive():
    assert AGLGateway("g").gateway_type is GatewayType.EXCLUSIVE


def test_agl_gateway_allows_exclusive_and_parallel():
    assert AGLGateway("g", gateway_type=GatewayType.EXCLUSIVE).gateway_type is GatewayType.EXCLUSIVE
    assert AGLGateway("g", gateway_type=GatewayType.PARALLEL).gateway_type is GatewayType.PARALLEL


@pytest.mark.parametrize("bad", [GatewayType.INCLUSIVE, GatewayType.COMPLEX,
                                 GatewayType.EVENT_BASED])
def test_agl_gateway_rejects_non_agl_types(bad):
    with pytest.raises(ValueError):
        AGLGateway("g", gateway_type=bad)
    g = AGLGateway("g")
    with pytest.raises(ValueError):
        g.gateway_type = bad


def test_agl_gateway_gateway_type_type_checked():
    with pytest.raises(TypeError):
        AGLGateway("g", gateway_type="exclusive")


def test_agl_gateway_ref_class_and_logic_method_type_checked():
    with pytest.raises(TypeError):
        AGLGateway("g", ref_class="C")
    with pytest.raises(TypeError):
        AGLGateway("g", logic_method="evaluate")
    m = Method(name="evaluate", is_abstract=True)
    assert AGLGateway("g", logic_method=m).logic_method is m


def _wire(process, source, *targets):
    process.add_flow_node(source)
    for t in targets:
        if t.container is not process:
            process.add_flow_node(t)
        process.add_sequence_flow(SequenceFlow(source, t))


def test_control_role_decision_and_merge():
    """EXCLUSIVE: 1-in/N-out -> decision; N-in/1-out -> merge."""
    proc = Process("p")
    g = AGLGateway("g", gateway_type=GatewayType.EXCLUSIVE, ref_class=Class(name="C"))
    a, b = AGLTask("a", ref_class=Class(name="A")), AGLTask("b", ref_class=Class(name="B"))
    _wire(proc, g, a, b)  # g diverges to a, b
    assert g.control_role == "decision"

    proc2 = Process("p2")
    g2 = AGLGateway("g2", gateway_type=GatewayType.EXCLUSIVE, ref_class=Class(name="C"))
    x, y = AGLTask("x", ref_class=Class(name="X")), AGLTask("y", ref_class=Class(name="Y"))
    for n in (g2, x, y):
        proc2.add_flow_node(n)
    proc2.add_sequence_flow(SequenceFlow(x, g2))
    proc2.add_sequence_flow(SequenceFlow(y, g2))  # x, y converge into g2
    assert g2.control_role == "merge"


def test_control_role_fork_and_join():
    """PARALLEL: 1-in/N-out -> fork; N-in/1-out -> join."""
    proc = Process("p")
    g = AGLGateway("g", gateway_type=GatewayType.PARALLEL, ref_class=Class(name="C"))
    a, b = AGLTask("a", ref_class=Class(name="A")), AGLTask("b", ref_class=Class(name="B"))
    _wire(proc, g, a, b)
    assert g.control_role == "fork"

    proc2 = Process("p2")
    g2 = AGLGateway("g2", gateway_type=GatewayType.PARALLEL, ref_class=Class(name="C"))
    x, y = AGLTask("x", ref_class=Class(name="X")), AGLTask("y", ref_class=Class(name="Y"))
    for n in (g2, x, y):
        proc2.add_flow_node(n)
    proc2.add_sequence_flow(SequenceFlow(x, g2))
    proc2.add_sequence_flow(SequenceFlow(y, g2))
    assert g2.control_role == "join"


def test_control_role_none_when_ambiguous_or_unattached():
    """A gateway with no container (degree 0) or a 1-in/1-out pass-through is ambiguous."""
    assert AGLGateway("g").control_role is None
    proc = Process("p")
    g = AGLGateway("g", gateway_type=GatewayType.EXCLUSIVE)
    a = AGLTask("a", ref_class=Class(name="A"))
    b = AGLTask("b", ref_class=Class(name="B"))
    for n in (g, a, b):
        proc.add_flow_node(n)
    proc.add_sequence_flow(SequenceFlow(a, g))
    proc.add_sequence_flow(SequenceFlow(g, b))  # 1-in / 1-out
    assert g.control_role is None


# ---------------------------------------------------------------------------
# Group 4 -- AGLModel
# ---------------------------------------------------------------------------

def test_agl_model_is_a_bpmn_model_and_context_type_checked():
    from besser.BUML.metamodel.bpmn.bpmn import BPMNModel
    m = AGLModel("m")
    assert isinstance(m, BPMNModel)
    assert m.context is None
    with pytest.raises(TypeError):
        AGLModel("m", context="Activity")


def test_start_nodes_are_nodes_without_incoming(enrollment_model):
    starts = enrollment_model.start_nodes
    names = {n.name for n in starts}
    assert names == {"MStudent"}  # only the root action node has no incoming flow


def test_valid_model_passes(enrollment_model):
    result = enrollment_model.validate(raise_exception=False)
    assert result["success"], result["errors"]
    assert result["warnings"] == []


def test_a1_action_node_needs_ref_class(enrollment_model):
    """A1: an AGLTask with no ref_class is an error."""
    task = next(n for n in enrollment_model.all_flow_nodes() if n.name == "MHelpRequest")
    task.ref_class = None
    result = enrollment_model.validate(raise_exception=False)
    assert not result["success"]
    assert any("AGLTask 'MHelpRequest' has no ref_class" in e for e in result["errors"])


def test_a2_control_node_needs_ref_class(enrollment_model):
    """A2: an AGLGateway with no ref_class is an error."""
    gate = next(n for n in enrollment_model.all_flow_nodes() if n.name == "MDHelpOrSClass")
    gate.ref_class = None
    result = enrollment_model.validate(raise_exception=False)
    assert not result["success"]
    assert any("AGLGateway 'MDHelpOrSClass' has no ref_class" in e for e in result["errors"])


def test_a3_ase_state_matching_rejects_bad_order(enrollment_model):
    """A3: newObject -> open is invalid (newObject.post={NewObject} ⊄ open.pre={Init})."""
    task = next(n for n in enrollment_model.all_flow_nodes() if n.name == "MStudent")
    task.act_sequence = [ModuleAct.core(ActName.NEW_OBJECT), ModuleAct.core(ActName.OPEN)]
    result = enrollment_model.validate(raise_exception=False)
    assert not result["success"]
    assert any("is not a valid ASE" in e for e in result["errors"])


def test_a3_ase_accepts_valid_order(enrollment_model, valid_open_new):
    """A3: open -> newObject is valid; the model still passes."""
    task = next(n for n in enrollment_model.all_flow_nodes() if n.name == "MStudent")
    task.act_sequence = valid_open_new
    result = enrollment_model.validate(raise_exception=False)
    assert result["success"], result["errors"]


def test_a3_ase_equal_states_are_a_valid_subset():
    """Boundary: post == pre (equal sets) satisfies the ⊆ rule (pins != vs <)."""
    a = ModuleAct(ActName.OPEN, pre_states={State.INIT}, post_states={State.EDITING})
    b = ModuleAct(ActName.RESET, pre_states={State.EDITING}, post_states={State.RESET})
    task = AGLTask("t", ref_class=Class(name="C"), act_sequence=[a, b])
    proc = Process("p", flow_nodes={task})
    model = AGLModel("m", context=Class(name="Act"), processes={proc})
    assert model.validate(raise_exception=False)["success"]


def test_a3_ase_strict_superset_fails():
    """Boundary: post is a strict superset of the next pre -> not a subset -> error."""
    a = ModuleAct(ActName.OPEN, pre_states={State.INIT},
                  post_states={State.EDITING, State.CREATED})
    b = ModuleAct(ActName.RESET, pre_states={State.EDITING}, post_states={State.RESET})
    task = AGLTask("t", ref_class=Class(name="C"), act_sequence=[a, b])
    proc = Process("p", flow_nodes={task})
    model = AGLModel("m", context=Class(name="Act"), processes={proc})
    result = model.validate(raise_exception=False)
    assert not result["success"]
    assert any("is not a valid ASE" in e for e in result["errors"])


def test_a4_empty_act_sequence_warns():
    """A4: an action node with an empty act_sequence is a warning, not an error."""
    task = AGLTask("t", ref_class=Class(name="C"))  # bound but no actions
    proc = Process("p", flow_nodes={task})
    model = AGLModel("m", context=Class(name="Act"), processes={proc})
    result = model.validate(raise_exception=False)
    assert result["success"]  # not an error
    assert any("empty act_sequence" in w for w in result["warnings"])


def test_a5_missing_context_warns():
    """A5: a model without an activity class (context) is a warning."""
    task = AGLTask("t", ref_class=Class(name="C"), act_sequence=[ModuleAct.core(ActName.OPEN)])
    proc = Process("p", flow_nodes={task})
    model = AGLModel("m", processes={proc})  # no context
    result = model.validate(raise_exception=False)
    assert result["success"]
    assert any("has no context" in w for w in result["warnings"])


def test_validate_raises_by_default():
    """validate() raises ValueError on errors unless raise_exception=False."""
    task = AGLTask("t")  # no ref_class -> A1 error
    proc = Process("p", flow_nodes={task})
    model = AGLModel("m", context=Class(name="Act"), processes={proc})
    with pytest.raises(ValueError):
        model.validate()
    # does not raise when asked not to
    assert model.validate(raise_exception=False)["success"] is False


# ---------------------------------------------------------------------------
# Group 5 -- base BPMN rules still fire through AGLModel.validate()
# ---------------------------------------------------------------------------

def test_base_bpmn_rule_still_enforced_through_agl_model():
    """A SequenceFlow crossing container boundaries is a base rule (E2); AGLModel must
    still report it -- proving super().validate() is composed, not bypassed."""
    proc_a = Process("a")
    proc_b = Process("b")
    src = AGLTask("src", ref_class=Class(name="S"), act_sequence=[ModuleAct.core(ActName.OPEN)])
    dst = AGLTask("dst", ref_class=Class(name="D"), act_sequence=[ModuleAct.core(ActName.OPEN)])
    proc_a.add_flow_node(src)
    proc_b.add_flow_node(dst)
    cross = SequenceFlow(src, dst)
    proc_a.add_sequence_flow(cross)  # source in a, target in b -> E2 boundary error
    model = AGLModel("m", context=Class(name="Act"), processes={proc_a, proc_b})
    result = model.validate(raise_exception=False)
    assert not result["success"]
    assert any("crosses a process" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Group 6 -- __repr__ smoke (cheap, guards against crashes on None binding)
# ---------------------------------------------------------------------------

def test_reprs_do_not_crash_on_unbound_nodes():
    assert "AGLTask" in repr(AGLTask("t"))
    assert "AGLGateway" in repr(AGLGateway("g"))
    assert "AGLModel" in repr(AGLModel("m"))
    assert "ModuleAct" in repr(ModuleAct.core(ActName.OPEN))
