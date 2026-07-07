"""Shared fixtures for the activity-diagram metamodel tests.

Three well-formed models that must validate with zero errors:
- linear_activity_model:      Initial -> Action -> ActivityFinal
- decision_activity_model:    Initial -> Action -> Decision -{2 guarded}-> Merge -> Final
- concurrent_activity_model:  Initial -> Fork -{2 actions}-> Join -> Final

Guards are stringly OpaqueExpressions; the fixtures pass plain strings (which the
edge coerces into untagged expressions).
"""

import pytest

from besser.BUML.metamodel.activity import ActivityModel


@pytest.fixture
def linear_activity_model() -> ActivityModel:
    m = ActivityModel("Linear")
    i = m.new_initial("start")
    a = m.new_action("do_work")
    f = m.new_activity_final("done")
    m.connect(i, a)
    m.connect(a, f)
    return m


@pytest.fixture
def decision_activity_model() -> ActivityModel:
    m = ActivityModel("Decision")
    i = m.new_initial("start")
    a = m.new_action("step")
    d = m.new_decision("decide")
    b = m.new_action("branch_a")
    c = m.new_action("branch_b")
    mg = m.new_merge("merge")
    f = m.new_activity_final("end")
    m.connect(i, a)
    m.connect(a, d)
    m.connect(d, b, guard="guard_a")
    m.connect(d, c, guard="guard_b")
    m.connect(b, mg)
    m.connect(c, mg)
    m.connect(mg, f)
    return m


@pytest.fixture
def concurrent_activity_model() -> ActivityModel:
    m = ActivityModel("Concurrent")
    i = m.new_initial("start")
    fk = m.new_fork("split")
    a1 = m.new_action("task_a")
    a2 = m.new_action("task_b")
    jn = m.new_join("sync")
    f = m.new_activity_final("end")
    m.connect(i, fk)
    m.connect(fk, a1)
    m.connect(fk, a2)
    m.connect(a1, jn)
    m.connect(a2, jn)
    m.connect(jn, f)
    return m
