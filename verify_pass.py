"""Independent checks on the agent's raw output, before evaluator sanitizing."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from agent import Agent
from make_submission import build_submission
from mock_environment import make_mock_env
from scoring_core import CHANNELS, MAX_CAMPAIGNS, MAX_CUSTOMERS_PER_CAMPAIGN, TOTAL_BUDGET, apply_filters, validate_strategy


def _raw_campaign_check(campaigns, env):
    assert isinstance(campaigns, list), f"Agent.act returned {type(campaigns).__name__}, expected list"
    assert 1 <= len(campaigns) <= MAX_CAMPAIGNS, f"raw campaign count: {len(campaigns)}"
    validate_strategy(pd.DataFrame(campaigns), env.tariffs)
    sizes = []
    cost = 0
    contacts = 0
    reached = set()
    for i, campaign in enumerate(campaigns):
        assert isinstance(campaign, dict), f"campaign {i} is not a dict"
        segment = apply_filters(env.customer_profile, pd.Series(campaign))
        n = len(segment)
        assert 0 < n <= MAX_CUSTOMERS_PER_CAMPAIGN, f"campaign {i} selects {n} subscribers"
        ids = set(segment["ID_NUMBER"])
        overlap = reached.intersection(ids)
        assert not overlap, f"final campaign {i} overlaps {len(overlap)} earlier final contacts"
        reached.update(ids)
        sizes.append(n)
        contacts += n
        cost += n * CHANNELS[campaign["channel"]]["cost_per_contact"]
    return sizes, cost, contacts


def main():
    results = []
    agent_hash = hashlib.sha256(Path("agent.py").read_bytes()).hexdigest()
    for seed in range(10):
        env, internals = make_mock_env(seed=seed)
        agent = Agent()
        start = time.perf_counter()
        campaigns = agent.act(env)  # deliberately bypass local_eval's exception handler and sanitizer
        elapsed = time.perf_counter() - start
        assert elapsed < 300, f"seed {seed}: Agent.act took {elapsed:.2f}s"
        sizes, final_cost, final_contacts = _raw_campaign_check(campaigns, env)
        pilots = internals.executed_pilot_campaigns()
        assert 0 < len(pilots) <= 20, f"seed {seed}: pilot count {len(pilots)}"
        pilot_cost = 0
        pilot_contacts = 0
        for i, pilot in enumerate(pilots):
            n = len(pilot.get("explicit_ids", []))
            assert 10 <= n <= 200, f"seed {seed}: pilot {i} contact count {n}"
            assert pilot["channel"] in env.channels
            assert pilot["target_tariff"] in set(env.tariffs["tariff_plan_code"])
            pilot_contacts += n
            pilot_cost += n * env.channels[pilot["channel"]]["cost_per_contact"]
        total_cost = pilot_cost + final_cost
        total_contacts = pilot_contacts + final_contacts
        assert total_cost <= TOTAL_BUDGET, f"seed {seed}: raw cost {total_cost} exceeds {TOTAL_BUDGET}"
        assert total_contacts <= env.max_total_contacts, f"seed {seed}: raw reach {total_contacts} exceeds {env.max_total_contacts}"
        results.append({
            "seed": seed,
            "campaigns": len(campaigns),
            "campaign_sizes": sizes,
            "pilots": len(pilots),
            "pilot_contacts": pilot_contacts,
            "final_contacts": final_contacts,
            "total_contacts": total_contacts,
            "pilot_cost": pilot_cost,
            "final_cost": final_cost,
            "total_cost": total_cost,
            "agent_act_seconds": round(elapsed, 4),
        })

    first = build_submission(Agent()).to_csv(index=False, lineterminator="\n")
    second = build_submission(Agent()).to_csv(index=False, lineterminator="\n")
    assert first == second, "build_submission is not reproducible at seed=42"
    saved = Path("submission.csv").read_bytes().decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    assert saved == first, "checked-in submission.csv differs from current agent output (LF-normalized)"
    report = {
        "status": "PASS",
        "agent_sha256": agent_hash,
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "runs": results,
        "seed_42_submission_sha256_lf": hashlib.sha256(first.encode("utf-8")).hexdigest(),
        "submission_reproducible": True,
        "submission_matches_saved_file_lf_normalized": True,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
