"""AGL (Activity Graph Language) as a BPMN sibling extension.

A stereotype-as-subclass extension of the BPMN base metamodel that realizes the
**Activity Graph Language (AGL)** -- a class-bound behavioural DSL for Domain-Driven
Design (Dang/Le/Le, *AGL: Incorporating Behavioral Aspects into DDD*, IST 2023).

AGL is *formally* defined as a restricted domain of the UML activity graph language,
but its control-flow vocabulary (action node, decision / fork / join / merge control
nodes, directed guard-free edges) maps cleanly onto BPMN. Hosting it on BPMN reuses
BESSER's mature, editor-integrated BPMN base and the pure-addition sibling pattern
already proven by ``bpmn/agentic.py``. The base BPMN module (``bpmn.py``) is **not
modified** -- this file is a pure addition.

AGL's substance that BPMN does not carry is *added* here:

* domain binding on every node (``ref_class`` / ``service_class``) -- AGL's ``refCls`` /
  ``serviceCls`` (ASM, IST-2023 Fig 10);
* ``ModuleAct`` -- a SAA-typed module action with pre / post states (IST-2023 Def 6);
* ``AGLTask.act_sequence`` -- the ``actSeq`` an action node performs (ASM rule R1);
* control-node logic hooks -- AGL's ``Decision.evaluate()`` / ``Join.transf()`` are
  referenced as an abstract ``structural.Method`` (interfaces = abstract Class + abstract
  Method, the BESSER idiom -- no structural-metamodel change needed);
* the state-matching validity rule ``aᵢ.postStates ⊆ aᵢ₊₁.preStates`` (ASE, IST-2023 Def 4),
  added by ``AGLModel.validate()`` on top of the base BPMN rules.

Mapping (AGL ASM -> BPMN base):

    ActivityGraph      -> Process (flow_nodes + sequence_flows)
    Node (action)      -> AGLTask(Task)       + ref_class / service_class / act_sequence
    DecisionNode       -> AGLGateway(Gateway), gateway_type EXCLUSIVE  (1-in / N-out)
    MergeNode          -> AGLGateway(Gateway), gateway_type EXCLUSIVE  (N-in / 1-out)
    ForkNode           -> AGLGateway(Gateway), gateway_type PARALLEL   (1-in / N-out)
    JoinNode           -> AGLGateway(Gateway), gateway_type PARALLEL   (N-in / 1-out)
    Edge (guard-free)  -> SequenceFlow
    ActivityGraph.n0   -> derived start nodes (flow nodes with no incoming flow)
    activity class     -> AGLModel.context (the owning domain class)
"""

from enum import Enum

from besser.BUML.metamodel.bpmn.bpmn import (
    BPMNModel,
    Gateway,
    GatewayType,
    Task,
)
from besser.BUML.metamodel.structural import Class, Method


# ---------------------------------------------------------------------------
# Enumerations (IST-2023 §6.1: ActName and State)
# ---------------------------------------------------------------------------

class ActName(Enum):
    """The name of a core atomic action (IST-2023 §4.1, Table 1).

    These eight framework-level actions are AGL's fixed vocabulary of primitive
    module behaviours; a ``ModuleAct`` composes them into a SAA. Values match the
    camelCase action names used in the paper.
    """
    OPEN = "open"
    NEW_OBJECT = "newObject"
    SET_DATA_FIELD_VALUES = "setDataFieldValues"
    CREATE_OBJECT = "createObject"
    UPDATE_OBJECT = "updateObject"
    DELETE_OBJECT = "deleteObject"
    RESET = "reset"
    CANCEL = "cancel"


class State(Enum):
    """A module state -- a pre- or post-state of an action (IST-2023 §4.1).

    Covers both the normal states an action transitions between and the two
    *concurrent* qualifier states (``OBJ_IS_PRESENT`` / ``OBJ_IS_NOT_PRESENT``).
    The paper writes a compound pre-state such as "Editing + ObjIsNotPresent";
    Phase 0 flattens the concurrent qualifier into the pre-state set as a distinct
    member (a documented simplification -- see ``ModuleAct``).
    """
    INIT = "Init"
    OPENED = "Opened"
    NEW_OBJECT = "NewObject"
    EDITING = "Editing"
    CREATED = "Created"
    UPDATED = "Updated"
    RESET = "Reset"
    CANCELLED = "Cancelled"
    DELETED = "Deleted"
    # Concurrent qualifier states.
    OBJ_IS_PRESENT = "ObjIsPresent"
    OBJ_IS_NOT_PRESENT = "ObjIsNotPresent"


# Canonical pre- / post-states of the eight core atomic actions (IST-2023 Table 1).
# Concurrent qualifiers are flattened into the state sets (Phase 0 simplification).
_CORE_ACTION_STATES = {
    ActName.OPEN: (
        frozenset({State.INIT}),
        frozenset({State.OPENED}),
    ),
    ActName.NEW_OBJECT: (
        frozenset({State.OPENED, State.CREATED, State.UPDATED, State.RESET, State.CANCELLED}),
        frozenset({State.NEW_OBJECT}),
    ),
    ActName.SET_DATA_FIELD_VALUES: (
        frozenset({State.NEW_OBJECT, State.EDITING, State.CREATED, State.UPDATED,
                   State.RESET, State.CANCELLED}),
        frozenset({State.EDITING}),
    ),
    ActName.CREATE_OBJECT: (
        frozenset({State.NEW_OBJECT, State.EDITING, State.OBJ_IS_NOT_PRESENT}),
        frozenset({State.CREATED}),
    ),
    ActName.UPDATE_OBJECT: (
        frozenset({State.EDITING, State.OBJ_IS_PRESENT}),
        frozenset({State.UPDATED}),
    ),
    ActName.DELETE_OBJECT: (
        frozenset({State.CREATED, State.UPDATED, State.RESET, State.CANCELLED,
                   State.OBJ_IS_PRESENT}),
        frozenset({State.DELETED}),
    ),
    ActName.RESET: (
        frozenset({State.EDITING}),
        frozenset({State.RESET}),
    ),
    ActName.CANCEL: (
        frozenset({State.NEW_OBJECT, State.EDITING, State.OBJ_IS_NOT_PRESENT}),
        frozenset({State.CANCELLED}),
    ),
}


# ---------------------------------------------------------------------------
# ModuleAct -- a SAA-typed module action (IST-2023 Def 6, ASM)
# ---------------------------------------------------------------------------

class ModuleAct:
    """A structured atomic action (SAA) referenced by a node's ``act_sequence``
    (IST-2023 Def 6; ASM meta-concept ``ModuleAct``).

    A ``ModuleAct`` is the AGL substance BPMN does not model: it names a core action
    and records the module states it requires (``pre_states``) and reaches
    (``post_states``). The ASE validity rule ``aᵢ.postStates ⊆ aᵢ₊₁.preStates``
    (Def 4) is checked over an ``AGLTask.act_sequence`` by ``AGLModel.validate()``.

    Args:
        act_name (ActName): The core action this module action realizes.
        pre_states (set[State]): States the module must be in for the action to run.
        post_states (set[State]): States the action reaches on completion.
        name (str): Optional SAA label (defaults to the action name's value).
        output (str): Optional output specification. ``None`` when absent.
        field_names (list[str]): View data-field names set by the action.
        field_vals (list[str]): Values for the corresponding ``field_names`` entries.

    Attributes:
        act_name (ActName): The core action.
        pre_states (set[State]): The required pre-states.
        post_states (set[State]): The reached post-states.
        name (str): The SAA label.
        output (str): The output specification, or None.
        field_names (list[str]): The data-field names.
        field_vals (list[str]): The data-field values.
    """

    def __init__(self, act_name: "ActName", pre_states: set = None, post_states: set = None,
                 name: str = None, output: str = None,
                 field_names: list = None, field_vals: list = None):
        self.act_name = act_name
        self.pre_states = pre_states if pre_states is not None else set()
        self.post_states = post_states if post_states is not None else set()
        self.name = name if name is not None else act_name.value
        self.output = output
        self.field_names = field_names if field_names is not None else []
        self.field_vals = field_vals if field_vals is not None else []

    @classmethod
    def core(cls, act_name: "ActName", name: str = None, output: str = None,
             field_names: list = None, field_vals: list = None) -> "ModuleAct":
        """Build a ModuleAct for a core action with its canonical pre / post states
        from IST-2023 Table 1.

        Raises:
            TypeError: if act_name is not an ActName.
        """
        if not isinstance(act_name, ActName):
            raise TypeError(f"act_name must be an ActName, got {type(act_name).__name__}")
        pre, post = _CORE_ACTION_STATES[act_name]
        return cls(act_name, pre_states=set(pre), post_states=set(post),
                   name=name, output=output, field_names=field_names, field_vals=field_vals)

    @property
    def act_name(self) -> "ActName":
        """ActName: Get the core action this module action realizes."""
        return self.__act_name

    @act_name.setter
    def act_name(self, value: "ActName"):
        """ActName: Set the core action.

        Raises:
            TypeError: if not an ActName.
        """
        if not isinstance(value, ActName):
            raise TypeError(f"act_name must be an ActName, got {type(value).__name__}")
        self.__act_name = value

    @property
    def pre_states(self) -> set:
        """set[State]: Get the required pre-states."""
        return self.__pre_states

    @pre_states.setter
    def pre_states(self, value: set):
        """set[State]: Set the required pre-states.

        Raises:
            TypeError: if any element is not a State.
        """
        self.__pre_states = _checked_state_set(value, "pre_states")

    @property
    def post_states(self) -> set:
        """set[State]: Get the reached post-states."""
        return self.__post_states

    @post_states.setter
    def post_states(self, value: set):
        """set[State]: Set the reached post-states.

        Raises:
            TypeError: if any element is not a State.
        """
        self.__post_states = _checked_state_set(value, "post_states")

    @property
    def output(self):
        """str | None: Get the output specification, or None."""
        return self.__output

    @output.setter
    def output(self, value):
        """str | None: Set the output specification.

        Raises:
            TypeError: if value is neither a str nor None.
        """
        if value is not None and not isinstance(value, str):
            raise TypeError(f"output must be a str or None, got {type(value).__name__}")
        self.__output = value

    def __repr__(self):
        return (f"ModuleAct(name='{self.name}', act_name={self.act_name}, "
                f"pre_states={len(self.pre_states)}, post_states={len(self.post_states)})")


def _checked_state_set(values, label: str) -> set:
    """Coerce ``values`` to a set, raising TypeError if any element is not a State."""
    result = set(values)
    for value in result:
        if not isinstance(value, State):
            raise TypeError(
                f"{label} must contain State instances, got {type(value).__name__}"
            )
    return result


def _checked_class(value, label: str):
    """Type-check an optional structural.Class reference.

    Raises:
        TypeError: if value is neither a Class nor None.
    """
    if value is not None and not isinstance(value, Class):
        raise TypeError(f"{label} must be a Class or None, got {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# AGLTask -- an AGL action node
# ---------------------------------------------------------------------------

class AGLTask(Task):
    """An AGL action node -- a ``Task`` bound to a domain class and a module service,
    performing a sequence of module actions (ASM ``Node``, rule R1).

    Args:
        name (str): The node label (may be empty; inherited from BPMNElement).
        ref_class (Class): The referenced domain class (AGL ``refCls``). None until bound.
        service_class (Class): The ModuleService class through which the node performs
            its actions (AGL ``serviceCls``). None until bound.
        act_sequence (list[ModuleAct]): The module actions this node performs, in order
            (AGL ``actSeq``). Empty by default.
        task_type (TaskType): Inherited from Task.
        loop_characteristics (LoopCharacteristics): Inherited from Activity.
        layout (dict): Inherited (opaque DI passthrough).
        metadata, timestamp: Inherited.

    Attributes:
        ref_class (Class): The referenced domain class, or None.
        service_class (Class): The ModuleService class, or None.
        act_sequence (list[ModuleAct]): The ordered module actions.
    """

    def __init__(self, name: str = "", ref_class: "Class" = None,
                 service_class: "Class" = None, act_sequence: list = None,
                 task_type=None, loop_characteristics=None,
                 layout: dict = None, metadata=None, timestamp=None):
        super().__init__(name=name, task_type=task_type,
                         loop_characteristics=loop_characteristics,
                         layout=layout, metadata=metadata, timestamp=timestamp)
        self.ref_class = ref_class
        self.service_class = service_class
        self.act_sequence = act_sequence if act_sequence is not None else []

    @property
    def ref_class(self):
        """Class | None: Get the referenced domain class (AGL ``refCls``)."""
        return self.__ref_class

    @ref_class.setter
    def ref_class(self, value):
        """Class | None: Set the referenced domain class.

        Raises:
            TypeError: if value is neither a Class nor None.
        """
        self.__ref_class = _checked_class(value, "ref_class")

    @property
    def service_class(self):
        """Class | None: Get the ModuleService class (AGL ``serviceCls``)."""
        return self.__service_class

    @service_class.setter
    def service_class(self, value):
        """Class | None: Set the ModuleService class.

        Raises:
            TypeError: if value is neither a Class nor None.
        """
        self.__service_class = _checked_class(value, "service_class")

    @property
    def act_sequence(self) -> list:
        """list[ModuleAct]: Get the ordered module actions this node performs."""
        return self.__act_sequence

    @act_sequence.setter
    def act_sequence(self, value: list):
        """list[ModuleAct]: Set the ordered module actions.

        Raises:
            TypeError: if value is not a list, or any element is not a ModuleAct.
        """
        if not isinstance(value, list):
            raise TypeError(f"act_sequence must be a list, got {type(value).__name__}")
        for act in value:
            if not isinstance(act, ModuleAct):
                raise TypeError(
                    f"act_sequence must contain ModuleAct instances, got {type(act).__name__}"
                )
        self.__act_sequence = list(value)

    def __repr__(self):
        ref = self.ref_class.name if self.ref_class is not None else None
        return (f"AGLTask(name='{self.name}', ref_class={ref!r}, "
                f"act_sequence={len(self.act_sequence)})")


# ---------------------------------------------------------------------------
# AGLGateway -- an AGL control node
# ---------------------------------------------------------------------------

# AGL uses only decision / merge (EXCLUSIVE) and fork / join (PARALLEL) control
# nodes. INCLUSIVE / COMPLEX / EVENT_BASED gateways have no AGL counterpart; the
# gateway_type override restricts AGLGateway to the two eligible kinds.
_AGL_ELIGIBLE_GATEWAY_TYPES = frozenset({
    GatewayType.EXCLUSIVE,
    GatewayType.PARALLEL,
})


class AGLGateway(Gateway):
    """An AGL control node -- a ``Gateway`` bound to a control-component class, with an
    optional logic method (ASM ``ControlNode``).

    AGL's four control nodes map onto BPMN gateway type + topology:

    * ``DecisionNode`` -> EXCLUSIVE, 1-in / N-out (references ``Decision.evaluate()``);
    * ``MergeNode``    -> EXCLUSIVE, N-in / 1-out;
    * ``ForkNode``     -> PARALLEL,  1-in / N-out;
    * ``JoinNode``     -> PARALLEL,  N-in / 1-out (references ``Join.transf()``).

    Unlike the base ``Gateway``, an AGL control node is domain-bound (``ref_class``) and
    may carry a ``logic_method`` -- the abstract ``structural.Method`` realizing the
    node's decision / join logic (AGL's ``Decision`` / ``Join`` interfaces are modelled as
    an abstract ``Class`` with an abstract ``Method``, the BESSER idiom).

    Args:
        name (str): The gateway label (may be empty).
        gateway_type (GatewayType): EXCLUSIVE or PARALLEL only (default EXCLUSIVE).
        ref_class (Class): The control-component class (AGL ``refCls``). None until bound.
        logic_method (Method): The decision / join logic method, or None.
        layout (dict): Inherited.
        metadata, timestamp: Inherited.

    Attributes:
        ref_class (Class): The control-component class, or None.
        logic_method (Method): The decision / join logic method, or None.
        control_role (str): Derived -- "decision" / "merge" / "fork" / "join" / None
            (inferred from ``gateway_type`` and in / out degree; None when ambiguous).
    """

    def __init__(self, name: str = "", gateway_type: "GatewayType" = None,
                 ref_class: "Class" = None, logic_method: "Method" = None,
                 layout: dict = None, metadata=None, timestamp=None):
        super().__init__(name=name, gateway_type=gateway_type, layout=layout,
                         metadata=metadata, timestamp=timestamp)
        self.ref_class = ref_class
        self.logic_method = logic_method

    @Gateway.gateway_type.setter
    def gateway_type(self, value: "GatewayType"):
        """GatewayType: Set the gateway kind. Restricted to EXCLUSIVE or PARALLEL.

        Raises:
            TypeError: if not a GatewayType.
            ValueError: if not in {EXCLUSIVE, PARALLEL} (AGL has no INCLUSIVE / COMPLEX /
                EVENT_BASED control node).
        """
        if not isinstance(value, GatewayType):
            raise TypeError(
                f"gateway_type must be a GatewayType, got {type(value).__name__}"
            )
        if value not in _AGL_ELIGIBLE_GATEWAY_TYPES:
            raise ValueError(
                f"AGLGateway.gateway_type must be EXCLUSIVE or PARALLEL, got {value} "
                f"(AGL has no INCLUSIVE / COMPLEX / EVENT_BASED control node)"
            )
        # Write to the base's mangled slot, matching the AgenticGateway pattern.
        self._Gateway__gateway_type = value

    @property
    def ref_class(self):
        """Class | None: Get the control-component class (AGL ``refCls``)."""
        return self.__ref_class

    @ref_class.setter
    def ref_class(self, value):
        """Class | None: Set the control-component class.

        Raises:
            TypeError: if value is neither a Class nor None.
        """
        self.__ref_class = _checked_class(value, "ref_class")

    @property
    def logic_method(self):
        """Method | None: Get the decision / join logic method (AGL ``Decision.evaluate()``
        / ``Join.transf()``), or None."""
        return self.__logic_method

    @logic_method.setter
    def logic_method(self, value):
        """Method | None: Set the decision / join logic method.

        Raises:
            TypeError: if value is neither a Method nor None.
        """
        if value is not None and not isinstance(value, Method):
            raise TypeError(
                f"logic_method must be a Method or None, got {type(value).__name__}"
            )
        self.__logic_method = value

    @property
    def control_role(self):
        """str | None: Derived AGL control-node role, inferred from ``gateway_type`` and
        in / out degree: "decision" / "merge" (EXCLUSIVE) or "fork" / "join" (PARALLEL);
        None when the degree is ambiguous or the node is not yet in a container."""
        in_deg = len(self.incoming())
        out_deg = len(self.outgoing())
        diverging = in_deg <= 1 and out_deg >= 2
        converging = in_deg >= 2 and out_deg <= 1
        if self.gateway_type is GatewayType.EXCLUSIVE:
            if diverging:
                return "decision"
            if converging:
                return "merge"
        elif self.gateway_type is GatewayType.PARALLEL:
            if diverging:
                return "fork"
            if converging:
                return "join"
        return None

    def __repr__(self):
        ref = self.ref_class.name if self.ref_class is not None else None
        return (f"AGLGateway(name='{self.name}', gateway_type={self.gateway_type}, "
                f"ref_class={ref!r}, control_role={self.control_role})")


# ---------------------------------------------------------------------------
# AGLModel -- an activity graph configuration (AGC)
# ---------------------------------------------------------------------------

class AGLModel(BPMNModel):
    """The root of an AGL model -- an activity graph configuration (AGC).

    A ``BPMNModel`` whose action / control nodes are ``AGLTask`` / ``AGLGateway`` bound to
    an activity class (``context``). ``validate()`` runs the full base BPMN rule set and
    then *adds* AGL rules: binding-completeness on nodes and the ASE state-matching rule
    ``aᵢ.postStates ⊆ aᵢ₊₁.preStates`` (IST-2023 Def 4).

    Args:
        name (str): The model name.
        context (Class): The activity class this graph describes (AGL activity class /
            UML ``Behavior.context``). None until bound.
        processes, collaboration, data_stores, metadata, timestamp: Inherited from BPMNModel.

    Attributes:
        context (Class): The owning activity class, or None.
        start_nodes (set[FlowNode]): Derived -- nodes with no incoming sequence flow
            (AGL ``ActivityGraph.n0``).
    """

    def __init__(self, name: str, context: "Class" = None, processes: set = None,
                 collaboration=None, data_stores: set = None, metadata=None, timestamp=None):
        super().__init__(name=name, processes=processes, collaboration=collaboration,
                         data_stores=data_stores, metadata=metadata, timestamp=timestamp)
        self.context = context

    @property
    def context(self):
        """Class | None: Get the owning activity class (AGL activity class)."""
        return self.__context

    @context.setter
    def context(self, value):
        """Class | None: Set the owning activity class.

        Raises:
            TypeError: if value is neither a Class nor None.
        """
        self.__context = _checked_class(value, "context")

    @property
    def start_nodes(self) -> set:
        """set[FlowNode]: The graph's start nodes -- flow nodes with no incoming sequence
        flow (AGL ``ActivityGraph.n0``)."""
        return {node for node in self.all_flow_nodes() if not node.incoming()}

    def agl_nodes(self) -> set:
        """set[FlowNode]: Every AGLTask / AGLGateway in the model."""
        return {node for node in self.all_flow_nodes()
                if isinstance(node, (AGLTask, AGLGateway))}

    # --- validation --------------------------------------------------------

    def validate(self, raise_exception: bool = True) -> dict:
        """Validate the AGL model: the full base BPMN rule set plus AGL rules.

        Args:
            raise_exception (bool): If True, raise ValueError when validation fails.

        Returns:
            dict: ``{"success": bool, "errors": list[str], "warnings": list[str]}``.
        """
        base = super().validate(raise_exception=False)
        errors: list = list(base["errors"])
        warnings: list = self._relax_base_warnings(base["warnings"])

        self._validate_action_binding(errors)
        self._validate_control_binding(errors)
        self._validate_ase_state_matching(errors)
        self._warn_agl_smells(warnings)

        result = {"success": len(errors) == 0, "errors": errors, "warnings": warnings}
        if errors and raise_exception:
            raise ValueError("\n".join(errors))
        return result

    def _relax_base_warnings(self, base_warnings: list) -> list:
        """Drop the two base BPMN warnings that are false positives for a faithful AGL
        graph (the minimal, expected AGL relaxation):

        * W1 ("has no start event") -- AGL has no StartEvent; entry is the ``n0`` subset.
        * W2 ("unreachable") -- in AGL a node with no incoming flow *is* a start node
          (``ActivityGraph.n0``), not an unreachable smell.

        All other base warnings (e.g. an empty process, a dangling default flow) are kept.
        """
        return [w for w in base_warnings
                if "has no start event" not in w and "unreachable" not in w]

    def _validate_action_binding(self, errors: list):
        """A1: every AGLTask (action node) references a domain class (``ref_class``)."""
        for node in self.all_flow_nodes():
            if isinstance(node, AGLTask) and node.ref_class is None:
                errors.append(
                    f"AGLTask '{node.name}' has no ref_class; an AGL action node must "
                    f"reference a domain class."
                )

    def _validate_control_binding(self, errors: list):
        """A2: every AGLGateway (control node) references a control-component class."""
        for node in self.all_flow_nodes():
            if isinstance(node, AGLGateway) and node.ref_class is None:
                errors.append(
                    f"AGLGateway '{node.name}' has no ref_class; an AGL control node must "
                    f"reference a control-component class."
                )

    def _validate_ase_state_matching(self, errors: list):
        """A3: within an action node's ``act_sequence``, each action's post-states are a
        subset of the next action's pre-states (ASE validity, IST-2023 Def 4)."""
        for node in self.all_flow_nodes():
            if not isinstance(node, AGLTask):
                continue
            sequence = node.act_sequence
            for i in range(len(sequence) - 1):
                current = sequence[i]
                nxt = sequence[i + 1]
                if not current.post_states <= nxt.pre_states:
                    errors.append(
                        f"AGLTask '{node.name}' act_sequence is not a valid ASE: "
                        f"'{current.name}' post-states are not a subset of '{nxt.name}' "
                        f"pre-states (position {i})."
                    )

    def _warn_agl_smells(self, warnings: list):
        """A4: an action node with no module actions. A5: the model has no activity class."""
        if self.__context is None:
            warnings.append(
                f"AGLModel '{self.name}' has no context (activity class)."
            )
        for node in self.all_flow_nodes():
            if isinstance(node, AGLTask) and not node.act_sequence:
                warnings.append(
                    f"AGLTask '{node.name}' has an empty act_sequence "
                    f"(an AGL action node performs a sequence of module actions)."
                )

    def __repr__(self):
        ctx = self.context.name if self.context is not None else None
        return (f"AGLModel(name='{self.name}', context={ctx!r}, "
                f"processes={len(self.processes)})")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "ActName",
    "State",
    # Classes
    "ModuleAct",
    "AGLTask",
    "AGLGateway",
    "AGLModel",
]
