"""General-purpose, class-bindable UML Activity Diagram metamodel for BESSER.

This is a **general-purpose** activity/flow language in the B-UML family. It is
usable standalone (a plain control-flow diagram for documentation, interchange,
and structural validation) yet **class-bindable**: executable nodes may bind to
the class diagram (``ref_class``/``ref_method``/``ref_property``) and the whole
activity may declare an owning ``context`` class, so it can also specify domain
behaviour. Heavier, opinionated semantics (mandatory binding, OCL contracts,
state-matching, restricted node profiles) belong to a specialized layer that
subclasses this base in a sibling module -- mirroring ``state_machine`` -> ``agent``.

Guards and action bodies are **stringly** :class:`OpaqueExpression` values (a
``body`` string plus an optional ``language`` tag), not executable code. Unbound,
the body is a human-readable label ("payment approved"); class-bound, it can be
an OCL expression evaluated against the domain model. This keeps the general
model executable-free and single-language; a specialized layer attaches
evaluation/analysis semantics through the ``language`` tag.

v1 scope (control-flow core):
    Container:  ActivityModel (optionally bound to an owning ``context`` Class)
    Element:    ActivityElement base (shared ``layout`` interchange passthrough)
    Nodes:      InitialNode, ActivityFinalNode, FlowFinalNode, OpaqueAction,
                DecisionNode, MergeNode, ForkNode, JoinNode
    Edges:      ControlFlow (with a stringly guard)
    Guards/body: OpaqueExpression (stringly body + optional language tag)

Object flows/nodes/pins, event & call actions, structured nodes, and
swimlanes/partitions are deferred; the abstract grouping classes (ControlNode,
FinalNode, ExecutableNode, Action) are declared now so the hierarchy stays stable
and specialized profiles can subclass it in a separate module without a base refactor.

Design notes:
    * Node names are identifier-safe (``NamedElement.name`` rejects spaces and
      hyphens) so a name is directly usable as a generated-code identifier / stable
      cross-reference; human-readable text goes in the free-form ``label`` attribute.
    * The class-diagram binding lives on :class:`ExecutableNode` (action/object-
      executing nodes), NOT on the abstract base -- control nodes route tokens and
      carry no domain binding (mirrors ``object.Instance.classifier`` placement).
    * Edges are the single source of truth (BPMN idiom): nodes expose derived
      ``incoming()``/``outgoing()`` computed from ``ActivityModel.edges``.
    * No ``__eq__``/``__hash__`` on nodes/edges: they use object identity (edges
      compare endpoints with ``is``); uniqueness is enforced by-name in the
      ``ActivityModel`` collection setters and factories.
    * Fully self-contained: imports only from ``structural`` and never from
      ``state_machine`` -- the general language stays decoupled from the
      agent-framework state machine so the two evolve independently.
"""

from typing import Optional, Union

from besser.BUML.metamodel.structural import (
    NamedElement,
    Model,
    Method,
    Class,
    Property,
    UNLIMITED_MAX_MULTIPLICITY,
)


# --------------------------------------------------------------------------- #
# Expression value type (stringly; guards and action bodies)
# --------------------------------------------------------------------------- #

class OpaqueExpression:
    """A stringly opaque expression: a ``body`` string plus an optional ``language`` tag.

    Models UML's ``OpaqueExpression`` for guards and action bodies. The body is
    free text whose meaning depends on ``language``: a natural-language label when
    the activity is unbound (documentation), or an OCL/other expression when it is
    bound to a class model. The general metamodel never evaluates it -- a guard is
    a value, not runnable code; a specialized class-bound layer attaches
    evaluation/analysis semantics via ``language``.

    Args:
        body (str): The expression text (None as default).
        language (str): Optional language tag, e.g. ``"OCL"`` (None as default,
            meaning an uninterpreted natural-language label).

    Attributes:
        body (str): The expression text.
        language (str): The optional language tag.
    """

    def __init__(self, body: str = None, language: str = None):
        self.body = body
        self.language = language

    @property
    def body(self) -> Optional[str]:
        """Optional[str]: Get the expression text."""
        return self.__body

    @body.setter
    def body(self, value):
        """Optional[str]: Set the expression text.

        Raises:
            TypeError: If ``value`` is neither a str nor None.
        """
        if value is not None and not isinstance(value, str):
            raise TypeError(f"OpaqueExpression body must be a str or None, got {type(value).__name__}")
        self.__body = value

    @property
    def language(self) -> Optional[str]:
        """Optional[str]: Get the language tag."""
        return self.__language

    @language.setter
    def language(self, value):
        """Optional[str]: Set the language tag.

        Raises:
            TypeError: If ``value`` is neither a str nor None.
        """
        if value is not None and not isinstance(value, str):
            raise TypeError(f"OpaqueExpression language must be a str or None, got {type(value).__name__}")
        self.__language = value

    def __eq__(self, other):
        return (isinstance(other, OpaqueExpression)
                and other.body == self.body and other.language == self.language)

    def __hash__(self):
        return hash((self.__body, self.__language))

    def __repr__(self):
        return f"OpaqueExpression(body={self.body!r}, language={self.language!r})"


def _as_expression(value) -> Optional[OpaqueExpression]:
    """Coerce ``None`` / a str / an :class:`OpaqueExpression` into an OpaqueExpression.

    A bare str is wrapped as an untagged expression (``language=None``) so callers
    can write ``guard="payment approved"`` ergonomically.

    Raises:
        TypeError: If ``value`` is not None, a str, or an OpaqueExpression.
    """
    if value is None or isinstance(value, OpaqueExpression):
        return value
    if isinstance(value, str):
        return OpaqueExpression(body=value)
    raise TypeError(
        f"expected an OpaqueExpression, str, or None, got {type(value).__name__}")


# --------------------------------------------------------------------------- #
# Common element base
# --------------------------------------------------------------------------- #

class ActivityElement(NamedElement):
    """Abstract common base for all activity nodes and edges (mirrors ``bpmn.BPMNElement``).

    Centralizes the diagram-interchange ``layout`` passthrough shared by every
    activity element; the metamodel never interprets it. Serves as the single
    stable root type a specialized DSL can extend.

    Args:
        name (str): The identifier-safe name of the element.
        layout (dict): Opaque diagram-interchange data (position/size/etc.),
            never interpreted by the metamodel (None as default).
        metadata (Metadata): Metadata information for the element (None as default).
        visibility (str): Determines the kind of visibility of the element (public as default).
        timestamp (datetime): Object creation datetime (default is current time).

    Attributes:
        name (str): Inherited from :class:`NamedElement`, the identifier-safe name.
        layout (dict): Opaque diagram-interchange data (None as default).

    Raises:
        TypeError: If instantiated directly rather than through a concrete subclass.
    """

    def __init__(self, name: str, layout: dict = None, metadata=None, visibility: str = "public",
                 timestamp=None):
        if type(self) is ActivityElement:
            raise TypeError("ActivityElement is abstract; instantiate a node or edge subclass.")
        super().__init__(name, timestamp=timestamp, metadata=metadata, visibility=visibility)
        self.layout = layout

    @property
    def layout(self) -> Optional[dict]:
        """Optional[dict]: Get the opaque diagram-interchange layout data."""
        return self.__layout

    @layout.setter
    def layout(self, value):
        """Optional[dict]: Set the opaque diagram-interchange layout data.

        Raises:
            TypeError: If ``value`` is neither a dict nor None.
        """
        if value is not None and not isinstance(value, dict):
            raise TypeError(f"layout must be a dict or None, got {type(value).__name__}")
        self.__layout = value


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #

class ActivityNode(ActivityElement):
    """Abstract base for every activity node.

    ``name`` is identifier-safe (spaces/hyphens rejected by ``NamedElement``);
    put display text in ``label``. Open for subclassing so specialized profiles
    can extend it. The class-diagram binding is NOT here -- it lives on
    :class:`ExecutableNode`, so control nodes stay binding-free.

    Args:
        name (str): The identifier-safe name of the node.
        label (str): Free-form display text, not name-validated (None as default).
        activity (ActivityModel): Back-pointer set by the owning
            :class:`ActivityModel` (None as default).
        layout (dict): Inherited from :class:`ActivityElement`, opaque interchange
            data (None as default).
        metadata (Metadata): Metadata information for the node (None as default).
        visibility (str): Visibility of the node (public as default).
        timestamp (datetime): Object creation datetime (default is current time).

    Attributes:
        name (str): Inherited from :class:`NamedElement`, the identifier-safe name.
        label (str): Free-form display text (None as default).
        activity (ActivityModel): Back-pointer to the owning model (None as default).
        layout (dict): Inherited from :class:`ActivityElement` (None as default).

    Raises:
        TypeError: If instantiated directly rather than through a concrete subclass.
    """

    def __init__(self, name: str, label: str = None, activity: "ActivityModel" = None,
                 layout: dict = None, metadata=None, visibility: str = "public", timestamp=None):
        if type(self) is ActivityNode:
            raise TypeError("ActivityNode is abstract; instantiate a concrete subclass.")
        super().__init__(name, layout=layout, metadata=metadata, visibility=visibility,
                         timestamp=timestamp)
        self.label = label                # free-form display text (not name-validated)
        self.activity = activity          # back-pointer, set by ActivityModel

    # ----- derived topology (edges are the single source of truth) -----
    def incoming(self) -> set["ActivityEdge"]:
        """set[ActivityEdge]: Get the edges targeting this node, derived from the activity's edges."""
        if self.activity is None:
            return set()
        return {e for e in self.activity.edges if e.target is self}

    def outgoing(self) -> set["ActivityEdge"]:
        """set[ActivityEdge]: Get the edges leaving this node, derived from the activity's edges."""
        if self.activity is None:
            return set()
        return {e for e in self.activity.edges if e.source is self}

    def __repr__(self):
        return f"{type(self).__name__}(name='{self.name}')"


# ---- control nodes (pure token routers; no domain binding) ----

class ControlNode(ActivityNode):
    """Abstract grouping for control nodes (pure token routers).

    Args:
        name (str): The identifier-safe name of the node.
        **kwargs: Additional keyword arguments forwarded to :class:`ActivityNode`.

    Raises:
        TypeError: If instantiated directly rather than through a concrete control node.
    """

    def __init__(self, name: str, **kwargs):
        if type(self) is ControlNode:
            raise TypeError("ControlNode is abstract; instantiate a concrete control node.")
        super().__init__(name, **kwargs)


class InitialNode(ControlNode):
    """Start of the flow.

    Topology: 0 incoming, >=1 outgoing (:class:`ControlFlow`).
    """


class FinalNode(ControlNode):
    """Abstract base for final nodes.

    Args:
        name (str): The identifier-safe name of the node.
        **kwargs: Additional keyword arguments forwarded to :class:`ControlNode`.

    Raises:
        TypeError: If instantiated directly; use :class:`ActivityFinalNode` or
            :class:`FlowFinalNode`.
    """

    def __init__(self, name: str, **kwargs):
        if type(self) is FinalNode:
            raise TypeError("FinalNode is abstract; use ActivityFinalNode or FlowFinalNode.")
        super().__init__(name, **kwargs)


class ActivityFinalNode(FinalNode):
    """Aborts the whole activity when reached."""


class FlowFinalNode(FinalNode):
    """Consumes a single token; other flows continue."""


class MergeNode(ControlNode):
    """Un-guarded token pass-through.

    Topology: >=2 incoming, 1 outgoing.
    """


class ForkNode(ControlNode):
    """Parallel split.

    Topology: 1 incoming, >=2 (un-guarded) outgoing.
    """


class DecisionNode(ControlNode):
    """Guarded branch.

    Topology: 1 incoming, >=2 outgoing each with a guard or one default.
    """


class JoinNode(ControlNode):
    """Parallel synchronization.

    Topology: >=2 incoming, 1 outgoing.
    """


# ---- executable nodes (carry the optional class-diagram binding + body) ----

class ExecutableNode(ActivityNode):
    """Abstract grouping for nodes that execute behaviour.

    Owns the optional, nullable class-diagram binding
    (``ref_class``/``ref_method``/``ref_property``) and the stringly ``body``
    (an :class:`OpaqueExpression`). Because the binding lives here, control nodes
    inherit none of it, and any future object node placed under this grouping
    inherits it for free.

    Args:
        name (str): The identifier-safe name of the node.
        body (OpaqueExpression): The action body/effect as a stringly expression;
            a plain str is accepted and wrapped (None as default).
        ref_class (Class): Optional structural :class:`Class` binding (None as default).
        ref_method (Method): Optional structural :class:`Method` binding (None as default).
        ref_property (Property): Optional structural :class:`Property` binding (None as default).
        **kwargs: Additional keyword arguments forwarded to :class:`ActivityNode`.

    Attributes:
        body (OpaqueExpression): The action body/effect (None as default).
        ref_class (Class): Optional structural class binding (None as default).
        ref_method (Method): Optional structural method binding (None as default).
        ref_property (Property): Optional structural property binding (None as default).

    Raises:
        TypeError: If instantiated directly rather than through a concrete subclass.
    """

    def __init__(self, name: str, body: Union["OpaqueExpression", str] = None,
                 ref_class: Class = None, ref_method: Method = None, ref_property: Property = None,
                 **kwargs):
        if type(self) is ExecutableNode:
            raise TypeError("ExecutableNode is abstract.")
        super().__init__(name, **kwargs)
        self.body = body                  # OpaqueExpression (str coerced)
        self.ref_class = ref_class        # Optional[structural.Class]  -- class-diagram binding
        self.ref_method = ref_method      # Optional[structural.Method]
        self.ref_property = ref_property  # Optional[structural.Property]

    @property
    def body(self) -> Optional[OpaqueExpression]:
        """Optional[OpaqueExpression]: Get the action body/effect expression."""
        return self.__body

    @body.setter
    def body(self, value):
        """Optional[OpaqueExpression]: Set the action body (a str is wrapped as an untagged expression).

        Raises:
            TypeError: If ``value`` is not an OpaqueExpression, str, or None.
        """
        self.__body = _as_expression(value)

    @property
    def ref_class(self) -> Optional[Class]:
        """Optional[Class]: Get the referenced structural class binding."""
        return self.__ref_class

    @ref_class.setter
    def ref_class(self, value):
        """Optional[Class]: Set the referenced structural class binding.

        Raises:
            TypeError: If ``value`` is neither a structural :class:`Class` nor None.
        """
        if value is not None and not isinstance(value, Class):
            raise TypeError(f"ref_class must be a structural.Class or None, got {type(value).__name__}")
        self.__ref_class = value

    @property
    def ref_method(self) -> Optional[Method]:
        """Optional[Method]: Get the referenced structural method binding."""
        return self.__ref_method

    @ref_method.setter
    def ref_method(self, value):
        """Optional[Method]: Set the referenced structural method binding.

        Raises:
            TypeError: If ``value`` is neither a structural :class:`Method` nor None.
        """
        if value is not None and not isinstance(value, Method):
            raise TypeError(f"ref_method must be a structural.Method or None, got {type(value).__name__}")
        self.__ref_method = value

    @property
    def ref_property(self) -> Optional[Property]:
        """Optional[Property]: Get the referenced structural property binding."""
        return self.__ref_property

    @ref_property.setter
    def ref_property(self, value):
        """Optional[Property]: Set the referenced structural property binding.

        Raises:
            TypeError: If ``value`` is neither a structural :class:`Property` nor None.
        """
        if value is not None and not isinstance(value, Property):
            raise TypeError(f"ref_property must be a structural.Property or None, got {type(value).__name__}")
        self.__ref_property = value


class Action(ExecutableNode):
    """Abstract base for actions (the executable steps).

    Args:
        name (str): The identifier-safe name of the node.
        **kwargs: Additional keyword arguments forwarded to :class:`ExecutableNode`.

    Raises:
        TypeError: If instantiated directly; use :class:`OpaqueAction`.
    """

    def __init__(self, name: str, **kwargs):
        if type(self) is Action:
            raise TypeError("Action is abstract; use OpaqueAction.")
        super().__init__(name, **kwargs)


class OpaqueAction(Action):
    """The default executable action, optionally carrying a stringly ``body`` and a class binding.

    Args:
        name (str): The identifier-safe name of the node.
        body (OpaqueExpression): Optional stringly body; a str is wrapped (None as default).
        **kwargs: Additional keyword arguments forwarded to :class:`ExecutableNode`
            (``ref_class``, ``ref_method``, ``ref_property``, ``label``, ...).
    """

    def __init__(self, name: str, body: Union["OpaqueExpression", str] = None, **kwargs):
        super().__init__(name, body=body, **kwargs)


# --------------------------------------------------------------------------- #
# Edges
# --------------------------------------------------------------------------- #

class ActivityEdge(ActivityElement):
    """Abstract directed edge between two activity nodes.

    Carries an optional stringly ``guard`` (an :class:`OpaqueExpression`) and a
    ``weight``. ``is_default`` marks a :class:`DecisionNode`'s "else" branch
    (which must have ``guard is None``).

    Args:
        source (ActivityNode): The source endpoint of the edge.
        target (ActivityNode): The target endpoint of the edge.
        name (str): The name of the edge ("e" as default).
        guard (OpaqueExpression): Optional stringly guard; a plain str is accepted
            and wrapped (None as default).
        weight (Union[int, str]): Token weight; ``"*"`` maps to
            ``UNLIMITED_MAX_MULTIPLICITY`` (1 as default).
        is_default (bool): Marks a :class:`DecisionNode`'s "else" branch (False as default).
        activity (ActivityModel): Back-pointer to the owning model (None as default).
        layout (dict): Inherited from :class:`ActivityElement` (None as default).
        metadata (Metadata): Metadata information for the edge (None as default).
        visibility (str): Determines the visibility of the edge (public as default).
        timestamp (datetime): Object creation datetime (default is current time).

    Attributes:
        source (ActivityNode): The source endpoint of the edge.
        target (ActivityNode): The target endpoint of the edge.
        guard (OpaqueExpression): Optional stringly guard (None as default).
        weight (int): Token weight (1 as default).
        is_default (bool): Marks a :class:`DecisionNode`'s "else" branch (False as default).
        activity (ActivityModel): Back-pointer to the owning model (None as default).

    Raises:
        TypeError: If instantiated directly; use :class:`ControlFlow`.
    """

    def __init__(self, source: ActivityNode, target: ActivityNode, name: str = "e",
                 guard: Union["OpaqueExpression", str] = None, weight: Union[int, str] = 1,
                 is_default: bool = False, activity: "ActivityModel" = None,
                 layout: dict = None, metadata=None, visibility: str = "public", timestamp=None):
        if type(self) is ActivityEdge:
            raise TypeError("ActivityEdge is abstract; use ControlFlow.")
        super().__init__(name or "e", layout=layout, metadata=metadata, visibility=visibility,
                         timestamp=timestamp)
        self.activity = activity
        self.source = source
        self.target = target
        self.guard = guard
        self.weight = weight
        self.is_default = is_default

    def _check_endpoint(self, node):
        """Validate that an edge endpoint is an :class:`ActivityNode` or None.

        Raises:
            TypeError: If ``node`` is neither an :class:`ActivityNode` nor None.
        """
        if node is not None and not isinstance(node, ActivityNode):
            raise TypeError("Edge endpoints must be ActivityNode instances.")

    @property
    def source(self) -> ActivityNode:
        """ActivityNode: Get the source endpoint of the edge."""
        return self.__source

    @source.setter
    def source(self, node):
        """ActivityNode: Set the source endpoint of the edge.

        Raises:
            TypeError: If ``node`` is neither an :class:`ActivityNode` nor None.
        """
        self._check_endpoint(node)
        self.__source = node

    @property
    def target(self) -> ActivityNode:
        """ActivityNode: Get the target endpoint of the edge."""
        return self.__target

    @target.setter
    def target(self, node):
        """ActivityNode: Set the target endpoint of the edge.

        Raises:
            TypeError: If ``node`` is neither an :class:`ActivityNode` nor None.
        """
        self._check_endpoint(node)
        self.__target = node

    @property
    def guard(self) -> Optional[OpaqueExpression]:
        """Optional[OpaqueExpression]: Get the stringly guard on the edge."""
        return self.__guard

    @guard.setter
    def guard(self, value):
        """Optional[OpaqueExpression]: Set the guard (a str is wrapped as an untagged expression).

        Raises:
            TypeError: If ``value`` is not an OpaqueExpression, str, or None.
        """
        self.__guard = _as_expression(value)

    @property
    def weight(self) -> int:
        """int: Get the token weight of the edge."""
        return self.__weight

    @weight.setter
    def weight(self, value):
        """int: Set the token weight of the edge (``"*"`` maps to ``UNLIMITED_MAX_MULTIPLICITY``).

        Raises:
            ValueError: If ``value`` is not an ``int >= 1`` (or the ``"*"`` sentinel).
        """
        if value == "*":
            value = UNLIMITED_MAX_MULTIPLICITY
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("weight must be an int >= 1 (or '*').")
        self.__weight = value

    @property
    def is_default(self) -> bool:
        """bool: Get whether this edge is a DecisionNode's default ("else") branch."""
        return self.__is_default

    @is_default.setter
    def is_default(self, value):
        """bool: Set whether this edge is a DecisionNode's default ("else") branch.

        Raises:
            TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(f"is_default must be a bool, got {type(value).__name__}")
        self.__is_default = value

    def __repr__(self):
        s = self.source.name if self.source else None
        t = self.target.name if self.target else None
        return f"{type(self).__name__}(name='{self.name}', source='{s}', target='{t}')"


class ControlFlow(ActivityEdge):
    """A control-flow edge (the only edge kind in v1; ObjectFlow is deferred)."""


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #

class ActivityModel(Model):
    """Root container for an activity diagram (mirrors DomainModel / StateMachine).

    Holds ``nodes`` and ``edges`` sets; ``elements`` is the derived union. May
    optionally declare an owning ``context`` class (UML ``Behavior.context``),
    which is also the natural OCL evaluation context for a class-bound activity.
    Provides ``new_*`` node factories and ``connect`` for edges, plus a
    ``validate()`` returning ``{success, errors, warnings}``.

    Args:
        name (str): The name of the model.
        nodes (set): The set of :class:`ActivityNode` instances (empty set as default).
        edges (set): The set of :class:`ActivityEdge` instances (empty set as default).
        context (Class): Optional owning/behaviored :class:`Class` the activity
            specifies behaviour for (None as default -- a standalone activity).
        timestamp (datetime): Object creation datetime (default is current time).
        metadata (Metadata): Metadata information for the model (None as default).
        is_derived (bool): Inherited from :class:`NamedElement`, indicates whether the
            element is derived (False as default).
        uncertainty (float): Uncertainty level between 0 and 1 (0.0 as default).

    Attributes:
        name (str): Inherited from :class:`NamedElement`, the name of the model.
        nodes (set): The set of :class:`ActivityNode` instances (empty set as default).
        edges (set): The set of :class:`ActivityEdge` instances (empty set as default).
        context (Class): Optional owning class (None as default).
        elements (set): Inherited from :class:`Model`, the derived union of
            ``nodes`` and ``edges``.
    """

    def __init__(self, name: str, nodes: set = None, edges: set = None, context: Class = None,
                 timestamp=None, metadata=None, is_derived: bool = False, uncertainty: float = 0.0):
        super().__init__(name, timestamp, metadata, is_derived=is_derived, uncertainty=uncertainty)
        self.__initializing = True
        self._edge_counter = 0
        self.context = context
        self.nodes = nodes if nodes is not None else set()
        self.edges = edges if edges is not None else set()
        self.__initializing = False
        self._update_elements()

    # ----- owning-class binding -----
    @property
    def context(self) -> Optional[Class]:
        """Optional[Class]: Get the owning/behaviored class of the activity."""
        return self.__context

    @context.setter
    def context(self, value):
        """Optional[Class]: Set the owning/behaviored class of the activity.

        Raises:
            TypeError: If ``value`` is neither a structural :class:`Class` nor None.
        """
        if value is not None and not isinstance(value, Class):
            raise TypeError(f"context must be a structural.Class or None, got {type(value).__name__}")
        self.__context = value

    # ----- collections (validating setters) -----
    @property
    def nodes(self) -> set:
        """set: Get the set of activity nodes in the model."""
        return self.__nodes

    @nodes.setter
    def nodes(self, value):
        """set: Set the set of activity nodes in the model and back-link them.

        Raises:
            TypeError: If any element is not an :class:`ActivityNode`.
            ValueError: If node names are duplicated, or a node already belongs to
                a different activity.
        """
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
        """set: Get the set of activity edges in the model."""
        return self.__edges

    @edges.setter
    def edges(self, value):
        """set: Set the set of activity edges in the model and back-link them.

        Raises:
            TypeError: If any element is not an :class:`ActivityEdge`.
            ValueError: If an edge already belongs to a different activity.
        """
        value = value if value is not None else set()
        if not all(isinstance(e, ActivityEdge) for e in value):
            raise TypeError("All edges must be ActivityEdge instances.")
        foreign = [e for e in value if e.activity is not None and e.activity is not self]
        if foreign:
            raise ValueError(
                f"Edges already belong to a different activity: {[e.name for e in foreign]}.")
        self.__edges = set(value)
        for e in self.__edges:
            e.activity = self
        self._update_elements()

    def _update_elements(self):
        """Recompute ``elements`` as the union of ``nodes`` and ``edges`` (no-op while initializing)."""
        # __initializing is set in __init__ before the nodes/edges setters (which call
        # this) run, so it is always defined by the time we get here.
        if self.__initializing:
            return
        self.elements = self.nodes | self.edges

    # ----- node factories -----
    def add_node(self, node: ActivityNode) -> ActivityNode:
        """Add an existing node to the model and back-link it.

        Args:
            node (ActivityNode): The node to add.

        Returns:
            ActivityNode: The added node.

        Raises:
            TypeError: If ``node`` is not an :class:`ActivityNode`.
            ValueError: If the node already belongs to another activity, or a node
                with the same name already exists in this activity.
        """
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

    def new_action(self, name: str, body: Union["OpaqueExpression", str] = None, ref_class: Class = None,
                   ref_method: Method = None, ref_property: Property = None) -> OpaqueAction:
        """Create an :class:`OpaqueAction`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the action.
            body (OpaqueExpression): Optional stringly body; a str is wrapped (None as default).
            ref_class (Class): Optional structural :class:`Class` binding (None as default).
            ref_method (Method): Optional structural :class:`Method` binding (None as default).
            ref_property (Property): Optional structural :class:`Property` binding (None as default).

        Returns:
            OpaqueAction: The created and registered action.
        """
        return self.add_node(OpaqueAction(name, body=body, ref_class=ref_class,
                                          ref_method=ref_method, ref_property=ref_property))

    def new_initial(self, name: str) -> InitialNode:
        """Create an :class:`InitialNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            InitialNode: The created and registered node.
        """
        return self.add_node(InitialNode(name))

    def new_activity_final(self, name: str) -> ActivityFinalNode:
        """Create an :class:`ActivityFinalNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            ActivityFinalNode: The created and registered node.
        """
        return self.add_node(ActivityFinalNode(name))

    def new_flow_final(self, name: str) -> FlowFinalNode:
        """Create a :class:`FlowFinalNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            FlowFinalNode: The created and registered node.
        """
        return self.add_node(FlowFinalNode(name))

    def new_decision(self, name: str) -> DecisionNode:
        """Create a :class:`DecisionNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            DecisionNode: The created and registered node.
        """
        return self.add_node(DecisionNode(name))

    def new_merge(self, name: str) -> MergeNode:
        """Create a :class:`MergeNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            MergeNode: The created and registered node.
        """
        return self.add_node(MergeNode(name))

    def new_fork(self, name: str) -> ForkNode:
        """Create a :class:`ForkNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            ForkNode: The created and registered node.
        """
        return self.add_node(ForkNode(name))

    def new_join(self, name: str) -> JoinNode:
        """Create a :class:`JoinNode`, add it to the model, and return it.

        Args:
            name (str): The identifier-safe name of the node.

        Returns:
            JoinNode: The created and registered node.
        """
        return self.add_node(JoinNode(name))

    # ----- edge construction -----
    def add_edge(self, edge: ActivityEdge) -> ActivityEdge:
        """Add an existing edge to the model and back-link it.

        This low-level escape hatch stays permissive (it does not check that the
        endpoints belong to the activity) so the E10 dangling-edge validation
        rule remains reachable.

        Args:
            edge (ActivityEdge): The edge to add.

        Returns:
            ActivityEdge: The added edge.

        Raises:
            TypeError: If ``edge`` is not an :class:`ActivityEdge`.
            ValueError: If the edge already belongs to a different activity.
        """
        if not isinstance(edge, ActivityEdge):
            raise TypeError("edge must be an ActivityEdge instance.")
        if edge.activity is not None and edge.activity is not self:
            raise ValueError(
                f"Edge '{edge.name}' already belongs to activity '{edge.activity.name}'; "
                f"an edge cannot be shared between activities.")
        edge.activity = self
        self.__edges.add(edge)
        self._update_elements()
        return edge

    def connect(self, source: ActivityNode, target: ActivityNode,
                guard: Union["OpaqueExpression", str] = None,
                weight: Union[int, str] = 1, name: str = None, is_default: bool = False) -> ControlFlow:
        """Create a :class:`ControlFlow` between two existing nodes and register it.

        Both endpoints must already be nodes of this activity; use :meth:`add_edge`
        as the permissive low-level alternative.

        Args:
            source (ActivityNode): The source node, which must belong to this activity.
            target (ActivityNode): The target node, which must belong to this activity.
            guard (OpaqueExpression): Optional stringly guard; a str is wrapped (None as default).
            weight (Union[int, str]): Token weight; ``"*"`` maps to
                ``UNLIMITED_MAX_MULTIPLICITY`` (1 as default).
            name (str): Optional edge name; an auto-generated name is used when None
                (None as default).
            is_default (bool): Marks a :class:`DecisionNode`'s "else" branch (False as default).

        Returns:
            ControlFlow: The created and registered edge.

        Raises:
            ValueError: If ``source`` or ``target`` is not a node of this activity.
        """
        # Fail fast: both endpoints must already be nodes of this activity. add_edge()
        # stays permissive as the low-level escape hatch, so the E10 dangling-edge
        # validation rule remains reachable.
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
        """str: Generate and return the next auto-incremented edge name."""
        self._edge_counter += 1
        return f"e_{self._edge_counter}"

    # ----- accessors -----
    def initial_nodes(self) -> list:
        """list: Get the list of :class:`InitialNode` instances in the model."""
        return [n for n in self.__nodes if isinstance(n, InitialNode)]

    def get_node_by_name(self, name: str) -> Optional[ActivityNode]:
        """Look up a node by its name.

        Args:
            name (str): The node name to search for.

        Returns:
            Optional[ActivityNode]: The matching node, or None if not found.
        """
        return next((n for n in self.__nodes if n.name == name), None)

    # ----- validation -----
    def validate(self, raise_exception: bool = True) -> dict:
        """Validate the activity.

        Errors block success; warnings are advisory. Only structural/topological
        well-formedness is checked -- guard/body *content* is opaque and is never
        interpreted here.

        Args:
            raise_exception (bool): If True, raise on any error (True as default).

        Returns:
            dict: A ``{success, errors, warnings}`` mapping.

        Raises:
            ValueError: If ``raise_exception`` is True and there are errors; the
                message is the joined error strings.
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
        """list: Get the list of nodes that are instances of ``cls``."""
        return [n for n in self.__nodes if isinstance(n, cls)]

    def _validate_initial(self, errors, warnings):
        """Validate InitialNode presence and topology (E1-E3, W1)."""
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
        """Validate final-node topology (E4, W2)."""
        finals = self._nodes_of(FinalNode)
        for n in finals:
            if n.outgoing():
                errors.append(f"Final node '{n.name}' must not have outgoing edges.")  # E4
        if not finals:
            warnings.append(f"Activity '{self.name}' has no final node.")  # W2

    def _validate_decision(self, errors):
        """Validate DecisionNode fan-in/fan-out and per-branch rules (E5)."""
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
                    f"DecisionNode '{n.name}' default branch '{e.name}' must not "
                    f"carry a guard (it is the 'else').")  # E5

    def _validate_fork(self, errors):
        """Validate ForkNode fan-in/fan-out and unguarded out-branches (E6)."""
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
        """Validate JoinNode fan-in/fan-out (E7)."""
        for n in self._nodes_of(JoinNode):
            ins, outs = n.incoming(), n.outgoing()
            if len(ins) < 2:
                errors.append(f"JoinNode '{n.name}' must have at least 2 incoming edges (has {len(ins)}).")  # E7
            if len(outs) != 1:
                errors.append(f"JoinNode '{n.name}' must have exactly 1 outgoing edge (has {len(outs)}).")  # E7

    def _validate_merge(self, errors):
        """Validate MergeNode fan-in/fan-out and unguarded outgoing edge (E8)."""
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
        """Validate that guarded / default edges originate from a DecisionNode (E9, E5-adjacent)."""
        for e in self.__edges:
            if e.guard is not None and not isinstance(e.source, DecisionNode):
                errors.append(
                    f"Edge '{e.name}' has a guard but its source is not a DecisionNode.")  # E9
            if e.is_default and not isinstance(e.source, DecisionNode):
                errors.append(
                    f"Edge '{e.name}' is marked default but its source is not a DecisionNode.")  # E5-adjacent

    def _validate_edges(self, errors):
        """Validate edge endpoints exist and belong to the activity (E10)."""
        for e in self.__edges:
            if e.source is None or e.target is None:
                errors.append(f"Edge '{e.name}' has a missing endpoint.")  # E10
                continue
            if e.source not in self.__nodes:
                errors.append(f"Edge '{e.name}' source '{e.source.name}' is not part of activity '{self.name}'.")
            if e.target not in self.__nodes:
                errors.append(f"Edge '{e.name}' target '{e.target.name}' is not part of activity '{self.name}'.")

    def _validate_actions(self, errors):
        """Validate that every Action has incoming and outgoing edges (E14)."""
        for n in self._nodes_of(Action):
            if not n.incoming():
                errors.append(f"Action '{n.name}' has no incoming edge.")  # E14
            if not n.outgoing():
                errors.append(f"Action '{n.name}' has no outgoing edge.")  # E14

    def _validate_unique_names(self, errors):
        """Validate that node names are unique within the activity (E13).

        Not dead code: insertion (``add_node`` / the ``nodes`` setter) rejects
        duplicate names, but a post-insert rename (``node.name = <existing>``)
        bypasses that check and is only caught here.
        """
        names = [n.name for n in self.__nodes]
        dups = sorted({x for x in names if names.count(x) > 1})
        if dups:
            errors.append(f"Duplicate node names in activity '{self.name}': {dups}.")  # E13

    def _validate_reachability(self, warnings):
        """Warn about nodes unreachable from any InitialNode (W3)."""
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
