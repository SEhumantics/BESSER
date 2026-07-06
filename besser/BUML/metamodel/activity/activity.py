"""Self-contained UML Activity Diagram metamodel for BESSER.

This module mirrors the ``state_machine`` metamodel *idiom* (nodes as
``NamedElement``, executable ``Condition`` guards, a ``validate()`` returning
``{success, errors, warnings}``, and the ``callable=``/``source=`` round-trip
discipline) but is **fully self-contained**: it imports only from the
``structural`` metamodel and never from ``state_machine``. In particular it
declares its own :class:`Condition` (copying the state_machine pattern) so the
activity package has zero coupling to state_machine.

v1 scope (control-flow core):
    Container:  ActivityModel
    Nodes:      InitialNode, ActivityFinalNode, FlowFinalNode, OpaqueAction,
                DecisionNode, MergeNode, ForkNode, JoinNode
    Edges:      ControlFlow (guarded)
    Guards:     Condition (executable Python bool, NOT OCL)
    Body:       OpaqueBehavior

Object flows/nodes/pins, event & call actions, and swimlanes/partitions are
deferred to v2; the abstract grouping classes (ControlNode, FinalNode,
ExecutableNode, Action) are declared now so the hierarchy stays stable and
specialized profiles can subclass it in a separate module without a base refactor.

Design notes:
    * Node names are identifier-safe (``NamedElement.name`` rejects spaces and
      hyphens); human-readable text goes in the free-form ``label`` attribute.
    * Edges are the single source of truth (BPMN idiom): nodes expose derived
      ``incoming()``/``outgoing()`` computed from ``ActivityModel.edges``.
    * No ``__eq__``/``__hash__`` is defined; uniqueness is enforced by-name in
      the ``ActivityModel`` collection setters and factories.
    * Every ``ActivityNode`` carries an optional, nullable structural binding
      (``ref_class``/``ref_method``/``ref_property``) so an action can reference a
      domain ``Class``/``Method``/``Property`` (e.g. a call-operation action).
"""

import inspect
import textwrap
from typing import Callable, Optional, Union

from besser.BUML.metamodel.structural import (
    NamedElement,
    Model,
    Method,
    Parameter,
    Type,
    Class,
    Property,
    UNLIMITED_MAX_MULTIPLICITY,
)


# --------------------------------------------------------------------------- #
# Guard & behavior (self-contained; NOT imported from state_machine)
# --------------------------------------------------------------------------- #

class Condition(Method):
    """A boolean guard on a ``DecisionNode`` out-branch (and, in v2, an ObjectFlow).

    Self-contained copy of the ``state_machine.Condition`` pattern (locked
    decision: the activity package must not import state_machine). A condition
    is built from either a live ``callable`` (whose source is extracted via
    ``inspect.getsource`` — needs a real source file) or a raw ``source`` string
    (the serialization / JSON round-trip path). Serialized paths MUST use
    ``source=`` because there is no live callable after deserialization.

    Unlike state_machine's Condition there is no ``session`` parameter: the
    static activity metamodel has no runtime Session.
    """

    def __init__(self, name: str, callable: Callable = None, source: str = None):
        if callable is not None:
            code = inspect.getsource(callable)
        elif source is not None:
            code = textwrap.dedent(source)
        else:
            code = None
        super().__init__(
            name=name,
            parameters={Parameter(name='params', type=Type('dict'))},
            type=Type('bool'),
            code=code,
        )

    def __repr__(self):
        return f"Condition(name='{self.name}')"


class OpaqueBehavior(Method):
    """The executable Python body of an ``Action``.

    Mirrors :class:`Condition`'s dual ``callable=``/``source=`` constructor but
    returns no boolean and carries no type. This is the generic ``body`` seam
    that specialized profiles can extend.
    """

    def __init__(self, name: str, callable: Callable = None, source: str = None):
        if callable is not None:
            code = inspect.getsource(callable)
        elif source is not None:
            code = textwrap.dedent(source)
        else:
            code = None
        super().__init__(
            name=name,
            parameters={Parameter(name='params', type=Type('dict'))},
            type=None,
            code=code,
        )

    def __repr__(self):
        return f"OpaqueBehavior(name='{self.name}')"


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

class ActivityNode(NamedElement):
    """Abstract base for every activity node.

    ``name`` is identifier-safe (spaces/hyphens rejected by ``NamedElement``);
    put display text in ``label``. Open for subclassing so specialized profiles
    can extend it. Carries the optional class-diagram binding and a generic
    ``body`` seam so no base refactor is needed to extend the hierarchy.
    """

    def __init__(self, name: str, label: str = None, activity: "ActivityModel" = None,
                 ref_class: Class = None, ref_method: Method = None, ref_property: Property = None,
                 body: OpaqueBehavior = None, metadata=None, visibility: str = "public"):
        if type(self) is ActivityNode:
            raise TypeError("ActivityNode is abstract; instantiate a concrete subclass.")
        super().__init__(name, metadata=metadata, visibility=visibility)
        self.label = label                # free-form display text (not name-validated)
        self.activity = activity          # back-pointer, set by ActivityModel
        self.body = body                  # Optional[OpaqueBehavior]
        self.ref_class = ref_class        # Optional[structural.Class]     -- class-diagram binding
        self.ref_method = ref_method      # Optional[structural.Method]
        self.ref_property = ref_property  # Optional[structural.Property]

    # ----- class-diagram binding: nullable getters/setters (type-check when not None) -----
    @property
    def ref_class(self) -> Optional[Class]:
        return self.__ref_class

    @ref_class.setter
    def ref_class(self, value):
        if value is not None and not isinstance(value, Class):
            raise TypeError(f"ref_class must be a structural.Class or None, got {type(value).__name__}")
        self.__ref_class = value

    @property
    def ref_method(self) -> Optional[Method]:
        return self.__ref_method

    @ref_method.setter
    def ref_method(self, value):
        if value is not None and not isinstance(value, Method):
            raise TypeError(f"ref_method must be a structural.Method or None, got {type(value).__name__}")
        self.__ref_method = value

    @property
    def ref_property(self) -> Optional[Property]:
        return self.__ref_property

    @ref_property.setter
    def ref_property(self, value):
        if value is not None and not isinstance(value, Property):
            raise TypeError(f"ref_property must be a structural.Property or None, got {type(value).__name__}")
        self.__ref_property = value

    @property
    def body(self) -> Optional[OpaqueBehavior]:
        return self.__body

    @body.setter
    def body(self, value):
        if value is not None and not isinstance(value, OpaqueBehavior):
            raise TypeError(f"body must be an OpaqueBehavior or None, got {type(value).__name__}")
        self.__body = value

    # ----- derived topology (edges are the single source of truth) -----
    def incoming(self) -> set["ActivityEdge"]:
        if self.activity is None:
            return set()
        return {e for e in self.activity.edges if e.target is self}

    def outgoing(self) -> set["ActivityEdge"]:
        if self.activity is None:
            return set()
        return {e for e in self.activity.edges if e.source is self}

    def __repr__(self):
        return f"{type(self).__name__}(name='{self.name}')"


# ---- control nodes ----

class ControlNode(ActivityNode):
    """Abstract grouping for control nodes."""

    def __init__(self, name: str, **kwargs):
        if type(self) is ControlNode:
            raise TypeError("ControlNode is abstract; instantiate a concrete control node.")
        super().__init__(name, **kwargs)


class InitialNode(ControlNode):
    """Start of the flow: 0 incoming, >=1 outgoing (ControlFlow)."""


class FinalNode(ControlNode):
    """Abstract base for final nodes."""

    def __init__(self, name: str, **kwargs):
        if type(self) is FinalNode:
            raise TypeError("FinalNode is abstract; use ActivityFinalNode or FlowFinalNode.")
        super().__init__(name, **kwargs)


class ActivityFinalNode(FinalNode):
    """Aborts the whole activity when reached."""


class FlowFinalNode(FinalNode):
    """Consumes a single token; other flows continue."""


class MergeNode(ControlNode):
    """Un-guarded token pass-through: >=2 incoming, 1 outgoing."""


class ForkNode(ControlNode):
    """Parallel split: 1 incoming, >=2 (un-guarded) outgoing."""


class DecisionNode(ControlNode):
    """Guarded branch: 1 incoming, >=2 outgoing each with a guard or one default."""

    def __init__(self, name: str, decision_input: Optional[Condition] = None, **kwargs):
        super().__init__(name, **kwargs)
        self.decision_input = decision_input


class JoinNode(ControlNode):
    """Parallel synchronization: >=2 incoming, 1 outgoing."""

    def __init__(self, name: str, join_spec: Optional[Condition] = None, **kwargs):
        super().__init__(name, **kwargs)
        self.join_spec = join_spec


# ---- executable nodes ----

class ExecutableNode(ActivityNode):
    """Abstract grouping for nodes that execute behavior."""

    def __init__(self, name: str, **kwargs):
        if type(self) is ExecutableNode:
            raise TypeError("ExecutableNode is abstract.")
        super().__init__(name, **kwargs)


class Action(ExecutableNode):
    """Abstract base for actions (the executable steps)."""

    def __init__(self, name: str, **kwargs):
        if type(self) is Action:
            raise TypeError("Action is abstract; use OpaqueAction.")
        super().__init__(name, **kwargs)


class OpaqueAction(Action):
    """The default executable action, optionally carrying an OpaqueBehavior body."""

    def __init__(self, name: str, body: OpaqueBehavior = None, **kwargs):
        super().__init__(name, body=body, **kwargs)


# --------------------------------------------------------------------------- #
# Edges
# --------------------------------------------------------------------------- #

class ActivityEdge(NamedElement):
    """Abstract directed edge between two activity nodes.

    Carries an optional executable ``guard`` (a :class:`Condition`) and a
    ``weight``. ``is_default`` marks a DecisionNode's "else" branch (which must
    have ``guard is None``).
    """

    def __init__(self, source: ActivityNode, target: ActivityNode, name: str = "e",
                 guard: Condition = None, weight: Union[int, str] = 1,
                 is_default: bool = False, activity: "ActivityModel" = None, metadata=None):
        if type(self) is ActivityEdge:
            raise TypeError("ActivityEdge is abstract; use ControlFlow.")
        super().__init__(name or "e", metadata=metadata)
        self.activity = activity
        self.source = source
        self.target = target
        self.guard = guard
        self.weight = weight
        self.is_default = is_default

    def _check_endpoint(self, node):
        if node is not None and not isinstance(node, ActivityNode):
            raise TypeError("Edge endpoints must be ActivityNode instances.")

    @property
    def source(self) -> ActivityNode:
        return self.__source

    @source.setter
    def source(self, node):
        self._check_endpoint(node)
        self.__source = node

    @property
    def target(self) -> ActivityNode:
        return self.__target

    @target.setter
    def target(self, node):
        self._check_endpoint(node)
        self.__target = node

    @property
    def guard(self) -> Optional[Condition]:
        return self.__guard

    @guard.setter
    def guard(self, value):
        if value is not None and not isinstance(value, Condition):
            raise TypeError(f"guard must be a Condition or None, got {type(value).__name__}")
        self.__guard = value

    @property
    def weight(self) -> int:
        return self.__weight

    @weight.setter
    def weight(self, value):
        if value == "*":
            value = UNLIMITED_MAX_MULTIPLICITY
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("weight must be an int >= 1 (or '*').")
        self.__weight = value

    def __repr__(self):
        s = self.source.name if self.source else None
        t = self.target.name if self.target else None
        return f"{type(self).__name__}(name='{self.name}', source='{s}', target='{t}')"


class ControlFlow(ActivityEdge):
    """A control-flow edge (the only edge kind in v1; ObjectFlow is v2)."""


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #

class ActivityModel(Model):
    """Root container for an activity diagram (mirrors DomainModel / StateMachine).

    Holds ``nodes`` and ``edges`` sets; ``elements`` is the derived union.
    Provides ``new_*`` node factories and ``connect`` for edges, plus a
    ``validate()`` returning ``{success, errors, warnings}``.
    """

    def __init__(self, name: str, nodes: set = None, edges: set = None,
                 timestamp=None, metadata=None, is_derived: bool = False, uncertainty: float = 0.0):
        super().__init__(name, timestamp, metadata, is_derived=is_derived, uncertainty=uncertainty)
        self.__initializing = True
        self._edge_counter = 0
        self.nodes = nodes if nodes is not None else set()
        self.edges = edges if edges is not None else set()
        self.__initializing = False
        self._update_elements()

    # ----- collections (validating setters) -----
    @property
    def nodes(self) -> set:
        return self.__nodes

    @nodes.setter
    def nodes(self, value):
        value = value if value is not None else set()
        if not all(isinstance(n, ActivityNode) for n in value):
            raise TypeError("All nodes must be ActivityNode instances.")
        names = [n.name for n in value]
        dups = sorted({n for n in names if names.count(n) > 1})
        if dups:
            raise ValueError(f"Duplicate node names: {dups}")
        foreign = [n for n in value if n.activity is not None and n.activity is not self]
        if foreign:
            raise ValueError(
                f"Nodes already belong to a different activity: {[n.name for n in foreign]}.")
        self.__nodes = set(value)
        for n in self.__nodes:
            n.activity = self
        self._update_elements()

    @property
    def edges(self) -> set:
        return self.__edges

    @edges.setter
    def edges(self, value):
        value = value if value is not None else set()
        if not all(isinstance(e, ActivityEdge) for e in value):
            raise TypeError("All edges must be ActivityEdge instances.")
        self.__edges = set(value)
        for e in self.__edges:
            e.activity = self
        self._update_elements()

    def _update_elements(self):
        # __initializing is set in __init__ before the nodes/edges setters (which call
        # this) run, so it is always defined by the time we get here.
        if self.__initializing:
            return
        self.elements = self.nodes | self.edges

    # ----- node factories -----
    def add_node(self, node: ActivityNode) -> ActivityNode:
        if not isinstance(node, ActivityNode):
            raise TypeError("node must be an ActivityNode instance.")
        if node.activity is not None and node.activity is not self:
            raise ValueError(
                f"Node '{node.name}' already belongs to activity '{node.activity.name}'; "
                f"a node cannot be shared between activities.")
        if any(n.name == node.name for n in self.__nodes):
            raise ValueError(f"A node named '{node.name}' already exists in activity '{self.name}'.")
        node.activity = self
        self.__nodes.add(node)
        self._update_elements()
        return node

    def new_action(self, name: str, body: OpaqueBehavior = None, ref_class: Class = None,
                   ref_method: Method = None, ref_property: Property = None) -> OpaqueAction:
        return self.add_node(OpaqueAction(name, body=body, ref_class=ref_class,
                                          ref_method=ref_method, ref_property=ref_property))

    def new_initial(self, name: str) -> InitialNode:
        return self.add_node(InitialNode(name))

    def new_activity_final(self, name: str) -> ActivityFinalNode:
        return self.add_node(ActivityFinalNode(name))

    def new_flow_final(self, name: str) -> FlowFinalNode:
        return self.add_node(FlowFinalNode(name))

    def new_decision(self, name: str, decision_input: Optional[Condition] = None) -> DecisionNode:
        return self.add_node(DecisionNode(name, decision_input=decision_input))

    def new_merge(self, name: str) -> MergeNode:
        return self.add_node(MergeNode(name))

    def new_fork(self, name: str) -> ForkNode:
        return self.add_node(ForkNode(name))

    def new_join(self, name: str, join_spec: Optional[Condition] = None) -> JoinNode:
        return self.add_node(JoinNode(name, join_spec=join_spec))

    # ----- edge construction -----
    def add_edge(self, edge: ActivityEdge) -> ActivityEdge:
        if not isinstance(edge, ActivityEdge):
            raise TypeError("edge must be an ActivityEdge instance.")
        edge.activity = self
        self.__edges.add(edge)
        self._update_elements()
        return edge

    def connect(self, source: ActivityNode, target: ActivityNode, guard: Condition = None,
                weight: Union[int, str] = 1, name: str = None, is_default: bool = False) -> ControlFlow:
        # Fail fast: both endpoints must already be nodes of this activity (mirrors
        # state_machine.go_to). add_edge() stays permissive as the low-level escape
        # hatch, so the E10 dangling-edge validation rule remains reachable.
        if source not in self.__nodes:
            raise ValueError(
                f"connect(): source '{getattr(source, 'name', source)}' is not a node of "
                f"activity '{self.name}'; add it first.")
        if target not in self.__nodes:
            raise ValueError(
                f"connect(): target '{getattr(target, 'name', target)}' is not a node of "
                f"activity '{self.name}'; add it first.")
        edge = ControlFlow(source=source, target=target, name=name or self._e_name(),
                           guard=guard, weight=weight, is_default=is_default, activity=self)
        return self.add_edge(edge)

    def _e_name(self) -> str:
        self._edge_counter += 1
        return f"e_{self._edge_counter}"

    # ----- accessors -----
    def initial_nodes(self) -> list:
        return [n for n in self.__nodes if isinstance(n, InitialNode)]

    def get_node_by_name(self, name: str) -> Optional[ActivityNode]:
        return next((n for n in self.__nodes if n.name == name), None)

    # ----- validation -----
    def validate(self, raise_exception: bool = True) -> dict:
        """Validate the activity. Returns ``{success, errors, warnings}``.

        Errors block success; warnings are advisory. If ``raise_exception`` and
        there are errors, raises ``ValueError`` with the joined messages.
        """
        errors: list[str] = []
        warnings: list[str] = []

        self._validate_initial(errors, warnings)
        self._validate_final_nodes(errors, warnings)
        self._validate_decision(errors)
        self._validate_fork(errors)
        self._validate_join(errors)
        self._validate_merge(errors)
        self._validate_guards(errors)
        self._validate_edges(errors)
        self._validate_actions(errors)
        self._validate_unique_names(errors)
        self._validate_reachability(warnings)

        result = {"success": len(errors) == 0, "errors": errors, "warnings": warnings}
        if errors and raise_exception:
            raise ValueError("\n".join(errors))
        return result

    def _nodes_of(self, cls) -> list:
        return [n for n in self.__nodes if isinstance(n, cls)]

    def _validate_initial(self, errors, warnings):
        initials = self.initial_nodes()
        if not initials:
            errors.append(f"Activity '{self.name}' must have at least one InitialNode.")  # E1
        if len(initials) > 1:
            warnings.append(f"Activity '{self.name}' has more than one InitialNode.")  # W1
        for n in initials:
            if n.incoming():
                errors.append(f"InitialNode '{n.name}' must have no incoming edges.")  # E2
            if not n.outgoing():
                errors.append(f"InitialNode '{n.name}' must have at least one outgoing edge.")  # E3

    def _validate_final_nodes(self, errors, warnings):
        finals = self._nodes_of(FinalNode)
        for n in finals:
            if n.outgoing():
                errors.append(f"Final node '{n.name}' must not have outgoing edges.")  # E4
        if not finals:
            warnings.append(f"Activity '{self.name}' has no final node.")  # W2

    def _validate_decision(self, errors):
        for n in self._nodes_of(DecisionNode):
            ins, outs = n.incoming(), n.outgoing()
            if len(ins) != 1:
                errors.append(f"DecisionNode '{n.name}' must have exactly 1 incoming edge (has {len(ins)}).")  # E5
            if len(outs) < 2:
                errors.append(f"DecisionNode '{n.name}' must have at least 2 outgoing edges (has {len(outs)}).")  # E5
            self._validate_decision_branches(n, outs, errors)

    def _validate_decision_branches(self, n, outs, errors):
        """Per-out-branch guard/default rules for a DecisionNode (E5)."""
        defaults = [e for e in outs if e.is_default]
        if len(defaults) > 1:
            errors.append(f"DecisionNode '{n.name}' has more than one default branch.")  # E5
        for e in outs:
            if e.guard is None and not e.is_default:
                errors.append(
                    f"DecisionNode '{n.name}' out-branch '{e.name}' needs a guard or must be the default.")  # E5
            if e.is_default and e.guard is not None:
                errors.append(
                    f"DecisionNode '{n.name}' default branch '{e.name}' must not carry a guard (it is the 'else').")  # E5

    def _validate_fork(self, errors):
        for n in self._nodes_of(ForkNode):
            ins, outs = n.incoming(), n.outgoing()
            if len(ins) != 1:
                errors.append(f"ForkNode '{n.name}' must have exactly 1 incoming edge (has {len(ins)}).")  # E6
            if len(outs) < 2:
                errors.append(f"ForkNode '{n.name}' must have at least 2 outgoing edges (has {len(outs)}).")  # E6
            for e in outs:
                if e.guard is not None:
                    errors.append(f"ForkNode '{n.name}' out-branch '{e.name}' must not be guarded.")  # E6

    def _validate_join(self, errors):
        for n in self._nodes_of(JoinNode):
            ins, outs = n.incoming(), n.outgoing()
            if len(ins) < 2:
                errors.append(f"JoinNode '{n.name}' must have at least 2 incoming edges (has {len(ins)}).")  # E7
            if len(outs) != 1:
                errors.append(f"JoinNode '{n.name}' must have exactly 1 outgoing edge (has {len(outs)}).")  # E7

    def _validate_merge(self, errors):
        for n in self._nodes_of(MergeNode):
            ins, outs = n.incoming(), n.outgoing()
            if len(ins) < 2:
                errors.append(f"MergeNode '{n.name}' must have at least 2 incoming edges (has {len(ins)}).")  # E8
            if len(outs) != 1:
                errors.append(f"MergeNode '{n.name}' must have exactly 1 outgoing edge (has {len(outs)}).")  # E8
            # The merge's own outgoing edge must be unguarded. Incoming edges may
            # legitimately carry a guard when they originate from a DecisionNode
            # (a decision branch flowing straight into a merge); E9 guarantees any
            # guarded edge has a DecisionNode source, so incoming guards are safe.
            for e in outs:
                if e.guard is not None:
                    errors.append(f"MergeNode '{n.name}' outgoing edge '{e.name}' must not be guarded.")  # E8

    def _validate_guards(self, errors):
        for e in self.__edges:
            if e.guard is not None and not isinstance(e.source, DecisionNode):
                errors.append(
                    f"Edge '{e.name}' has a guard but its source is not a DecisionNode.")  # E9
            if e.is_default and not isinstance(e.source, DecisionNode):
                errors.append(
                    f"Edge '{e.name}' is marked default but its source is not a DecisionNode.")  # E5-adjacent

    def _validate_edges(self, errors):
        for e in self.__edges:
            if e.source is None or e.target is None:
                errors.append(f"Edge '{e.name}' has a missing endpoint.")  # E10
                continue
            if e.source not in self.__nodes:
                errors.append(f"Edge '{e.name}' source '{e.source.name}' is not part of activity '{self.name}'.")
            if e.target not in self.__nodes:
                errors.append(f"Edge '{e.name}' target '{e.target.name}' is not part of activity '{self.name}'.")

    def _validate_actions(self, errors):
        for n in self._nodes_of(Action):
            if not n.incoming():
                errors.append(f"Action '{n.name}' has no incoming edge.")  # E14
            if not n.outgoing():
                errors.append(f"Action '{n.name}' has no outgoing edge.")  # E14

    def _validate_unique_names(self, errors):
        names = [n.name for n in self.__nodes]
        dups = sorted({x for x in names if names.count(x) > 1})
        if dups:
            errors.append(f"Duplicate node names in activity '{self.name}': {dups}.")  # E13

    def _validate_reachability(self, warnings):
        initials = self.initial_nodes()
        if not initials:
            return
        reachable = set(initials)
        frontier = list(initials)
        while frontier:
            cur = frontier.pop()
            for e in cur.outgoing():
                if e.target is not None and e.target not in reachable:
                    reachable.add(e.target)
                    frontier.append(e.target)
        for n in self.__nodes:
            if n not in reachable and not isinstance(n, InitialNode):
                warnings.append(f"Node '{n.name}' is unreachable from any InitialNode.")  # W3

    def __repr__(self):
        return f"ActivityModel(name='{self.name}', nodes={len(self.nodes)}, edges={len(self.edges)})"
