from types import SimpleNamespace

import pandas as pd

from agent import Agent


def _make_env(tariffs=("tariff_1", "tariff_2"), pilots_left=1,
              remaining_contacts=400):
    profile = pd.DataFrame({
        "current_tariff": ["tariff_1"] * 200,
        "arpu_segment": ["MID"] * 200,
        "predicted_arpu": [1_000.0] * 200,
    })
    return SimpleNamespace(
        customer_profile=profile,
        tariffs=pd.DataFrame({"tariff_plan_code": list(tariffs)}),
        channels={"sms": {"cost_per_contact": 0, "conversion_multiplier": 1.0}},
        remaining_budget=0,
        remaining_contacts=remaining_contacts,
        pilots_left=pilots_left,
    )


def _agent_without_priors():
    agent = Agent()
    agent._priors = lambda: {}
    return agent


def test_boundary_positive_observation_selects_regular_campaign():
    env = _make_env()

    def run_pilot(**kwargs):
        assert kwargs["n_customers"] == 200
        env.remaining_contacts -= 200
        env.pilots_left -= 1
        return {"n_customers": 200, "observed_lift_ratio": 0.075}

    env.run_pilot = run_pilot
    agent = _agent_without_priors()

    campaigns = agent.act(env)

    assert campaigns[0]["campaign_name"] == "AIKYN_BILD_01"
    assert "fallback" not in agent.audit


def test_transient_pilot_failure_retries_once_when_counters_are_unchanged():
    env = _make_env()
    calls = 0

    def run_pilot(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        env.remaining_contacts -= kwargs["n_customers"]
        env.pilots_left -= 1
        return {"n_customers": kwargs["n_customers"], "observed_lift_ratio": 0.5}

    env.run_pilot = run_pilot
    campaigns = _agent_without_priors().act(env)

    assert calls == 2
    assert campaigns[0]["campaign_name"] == "AIKYN_BILD_01"


def test_pilot_failure_after_counter_change_is_not_retried():
    env = _make_env(
        tariffs=("tariff_1", "tariff_2", "tariff_3"),
        pilots_left=2,
        remaining_contacts=600,
    )
    targets = []

    def run_pilot(**kwargs):
        targets.append(kwargs["target_tariff"])
        env.remaining_contacts -= kwargs["n_customers"]
        env.pilots_left -= 1
        if len(targets) == 1:
            raise RuntimeError("failure after spending counters")
        return {"n_customers": kwargs["n_customers"], "observed_lift_ratio": 0.5}

    env.run_pilot = run_pilot
    campaigns = _agent_without_priors().act(env)

    assert targets == ["tariff_2", "tariff_3"]
    assert campaigns[0]["target_tariff"] == "tariff_3"


def test_complete_pilot_failure_returns_empty_plan_with_refusal_diagnostic():
    env = _make_env(pilots_left=5)
    calls = 0

    def run_pilot(**kwargs):
        nonlocal calls
        calls += 1
        raise ValueError("pilot unavailable")

    env.run_pilot = run_pilot
    agent = _agent_without_priors()

    campaigns = agent.act(env)

    assert calls == 2
    assert campaigns == []
    assert agent.audit["refusal"] == "No successful pilots; campaign plan withheld."


def test_repeat_pilots_cover_plausible_hypotheses_before_third_attempt():
    profile = pd.DataFrame({
        "current_tariff": ["tariff_1"] * 400,
        "arpu_segment": ["MID"] * 200 + ["HIGH"] * 200,
        "predicted_arpu": [10_000.0] * 200 + [1_000.0] * 200,
    })
    env = SimpleNamespace(
        customer_profile=profile,
        tariffs=pd.DataFrame({"tariff_plan_code": ["tariff_1", "tariff_2"]}),
        channels={"sms": {"cost_per_contact": 0, "conversion_multiplier": 1.0}},
        remaining_budget=0,
        remaining_contacts=1_000,
        pilots_left=4,
    )
    segments = []

    def run_pilot(**kwargs):
        segments.append(kwargs["filter_arpu_segment"])
        env.remaining_contacts -= kwargs["n_customers"]
        env.pilots_left -= 1
        return {"n_customers": kwargs["n_customers"], "observed_lift_ratio": 0.5}

    env.run_pilot = run_pilot

    _agent_without_priors().act(env)

    assert segments.count("MID") == 2
    assert segments.count("HIGH") == 2


def test_refinement_stops_when_resources_cannot_fund_another_pilot():
    env = _make_env(pilots_left=2, remaining_contacts=500)
    env.channels["sms"]["cost_per_contact"] = 4
    env.remaining_budget = 160
    calls = 0

    def run_pilot(**kwargs):
        nonlocal calls
        calls += 1
        count = kwargs["n_customers"]
        cost = count * env.channels[kwargs["channel"]]["cost_per_contact"]
        assert cost <= env.remaining_budget
        env.remaining_budget -= cost
        env.remaining_contacts -= count
        env.pilots_left -= 1
        return {"n_customers": count, "observed_lift_ratio": 0.5}

    env.run_pilot = run_pilot

    campaigns = _agent_without_priors().act(env)

    assert calls == 1
    assert env.remaining_budget == 0
    assert env.remaining_contacts == 460
    assert env.pilots_left == 1
    assert campaigns == []
