# Activity Diagram — implementation roadmap & backlog

Self-contained UML Activity Diagram metamodel for BESSER. Built general-first and kept
domain-neutral: the node/edge hierarchy is open for subclassing, so specialized profiles
can extend it in a separate module without changing this package.

## Phase status

- [x] **Phase 0 — Metamodel + `validate()`** — `activity.py` + `__init__.py`. Self-contained
      (zero `state_machine` import; own `Condition`/`OpaqueBehavior`, no `session` param).
      Control-flow core nodes/edges, nullable class-diagram binding, `{success, errors, warnings}`
      contract with E/W rules. Adversarially reviewed; 48 tests green. **Done.**
- [ ] **Phase 1 — JSON⇄BUML converters** — symmetric pair with round-trip (TDD):
      `services/converters/json_to_buml/activity_diagram_processor.py` ↔
      `services/converters/buml_to_json/activity_diagram_converter.py`; register in the
      `__init__.py` files; discriminator string `"ActivityDiagram"`.
- [ ] **Phase 2 — Project + router dispatch wiring** — `constants.py` discriminator, both
      project converters, `conversion_router` (`/export-buml`, `/get-json-model` auto-detect),
      `validation_router` (`/validate-diagram`).
- [ ] **Phase 3 — Generator** — *out of scope for v1* (like `state_machine`). Revisit later.
- [ ] **Phase 4 — Frontend palette** — extend the editor with explicit
      Decision / Join / FlowFinal node types (decision: *extend*, not infer). Separate submodule PR.
- [ ] **Phase 5 — Docs** — `buml_language`, `web_editor(_backend)` entries; `make html`.

## Metamodel — deferred items (intentional, from the Phase-0 review)

- [ ] **W6 no-default-decision warning** — not implemented. Keying on "no `is_default` branch"
      would warn on every well-formed *exhaustive* decision (noisy). Add only if the editor
      wants the advisory; key on "no default present" since exhaustiveness isn't statically provable.
- [ ] **Edge-name uniqueness** — not enforced. Nodes are unique by name; edges auto-name `e_N`,
      but an explicit duplicate `name=` to `connect()`/`add_edge()` is accepted. Enforce in
      `add_edge` if edge lookups-by-name are ever needed.
- [ ] **Post-insert node rename** — bypasses uniqueness. Uniqueness is checked at insertion;
      `node.name = <existing>` is accepted and only caught later by `validate()` (E13). Route
      renames through a container-aware setter if it becomes a real problem.
- [ ] **Guarded fork/merge edge double-fires** — a guarded Fork/Merge edge yields two error
      strings (the fork/merge rule + E9). Correct but noisy for a UI; centralize guard-legality
      into one rule if the editor needs single messages.
- [ ] **MergeNode E8 wording** — the impl forbids a guard only on the merge's *own outgoing*
      edge; a guarded *incoming* edge from a `DecisionNode` is intentionally allowed (UML-defensible).
      Keep, but reconcile the plan's literal "no edge guarded" wording.

## Test backlog (lower priority)

- [ ] `FlowFinalNode`: happy-path validates clean; E4 (outgoing edge) error; reachability.
- [ ] `callable=` constructor path for `Condition` and `OpaqueBehavior` (assert `inspect.getsource`).
- [ ] `weight` rejection for `bool` / `float` / `str` (only `weight=0` covered today).
- [ ] Bulk `nodes=` setter duplicate-name path (distinct from the `add_node` path already tested).
- [ ] Direct assertions for W2 (no final), E3 (Initial with no outgoing), E14 (Action missing
      incoming or outgoing) — currently only incidentally exercised.

## Locked design decisions (context for contributors)

- Package is **fully self-contained** — no `state_machine` import; its own `Condition`/`OpaqueBehavior`.
- Guards are **executable Python `Condition`**, not OCL. `callable=` needs a real source file;
  serialized / round-trip paths **must** use `source=`.
- **Class-diagram binding** (`ref_class`/`ref_method`/`ref_property`) is nullable and on the base
  `ActivityNode` — an action may reference a domain `Class`/`Method`/`Property`; a plain
  activity diagram leaves them `None`.
- Node `name` is identifier-safe (spaces/hyphens rejected); human-readable text goes in `label`.
- **Edges are the single source of truth**; nodes expose derived `incoming()`/`outgoing()`.
- No `__eq__`/`__hash__`; uniqueness enforced by-name in `ActivityModel` setters/factories.
