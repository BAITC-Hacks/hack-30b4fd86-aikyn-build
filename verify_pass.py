"""Independent acceptance checks for a participant checkout.

Run from this validation checkout, for example:
    python verify_pass.py --repo ..\\published-main

The checker deliberately calls Agent.act before evaluator sanitizing/capping.
It only uses the public environment and scoring APIs; it does not inspect
closures or organizer-only model state.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pandas as pd


def normalize(data):
    return data.replace(b"\r\n", b"\n")


def load_target(repo):
    repo = Path(repo).resolve()
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    return repo, {
        name: importlib.import_module(name)
        for name in ("agent", "mock_environment", "scoring_core", "make_submission")
    }


def check_raw_agent(modules):
    agent_module = modules["agent"]
    mock = modules["mock_environment"]
    scoring = modules["scoring_core"]
    rows = []
    for seed in range(10):
        env, _ = mock.make_mock_env(seed=seed)
        started = time.perf_counter()
        campaigns = agent_module.Agent().act(env)
        elapsed = time.perf_counter() - started
        assert elapsed < 300, f"seed {seed}: Agent.act took {elapsed:.2f}s"
        assert isinstance(campaigns, list) and 1 <= len(campaigns) <= 10
        strategy = pd.DataFrame(campaigns)
        scoring.validate_strategy(strategy, env.tariffs)

        final_ids = set()
        final_cost = final_contacts = 0
        for campaign in campaigns:
            segment = scoring.apply_filters(env.customer_profile, pd.Series(campaign))
            assert 0 < len(segment) <= 5000, (
                seed, campaign.get("campaign_name"), len(segment)
            )
            ids = set(segment["ID_NUMBER"])
            assert not final_ids.intersection(ids), f"seed {seed}: final overlap"
            final_ids.update(ids)
            final_contacts += len(segment)
            final_cost += len(segment) * env.channels[campaign["channel"]]["cost_per_contact"]

        pilots = env.pilot_history
        assert 0 < len(pilots) <= 20
        assert all(10 <= int(p["n_customers"]) <= 200 for p in pilots)
        pilot_contacts = sum(int(p["n_customers"]) for p in pilots)
        pilot_cost = sum(float(p["cost"]) for p in pilots)
        total_contacts = pilot_contacts + final_contacts
        total_cost = pilot_cost + final_cost
        assert total_contacts <= env.max_total_contacts
        assert total_cost <= env.total_budget
        rows.append({"seed": seed, "campaigns": len(campaigns),
                     "pilots": len(pilots), "cost": total_cost,
                     "contacts": total_contacts, "seconds": round(elapsed, 3)})
    return rows


def run_script(repo, name, *args):
    return subprocess.run([sys.executable, name, *args], cwd=repo,
                          capture_output=True, text=True)


def check_evaluator(repo):
    results = {}
    for args, key in [((), "local_eval"), (("--runs", "10"), "local_eval_runs10")]:
        started = time.perf_counter()
        result = run_script(repo, "local_eval.py", *args)
        results[key] = {"returncode": result.returncode,
                        "seconds": round(time.perf_counter() - started, 3)}
        output = result.stdout + result.stderr
        assert result.returncode == 0, output[-2000:]
        assert not any(marker in output for marker in (
            "Traceback", "Агент упал", "Exception", "[ERROR]", "[WARNING]"
        ))
        assert "отброшена" not in output
    return results


def check_reproducibility(repo, modules):
    submission = Path(repo) / "submission.csv"
    original = submission.read_bytes() if submission.exists() else None
    try:
        first_run = run_script(repo, "make_submission.py")
        assert first_run.returncode == 0, first_run.stderr
        first = normalize(submission.read_bytes())
        second_run = run_script(repo, "make_submission.py")
        assert second_run.returncode == 0, second_run.stderr
        second = normalize(submission.read_bytes())
        assert first == second, "make_submission.py is not reproducible"
        expected = modules["make_submission"].build_submission(
            modules["agent"].Agent()).to_csv(index=False).encode()
        assert normalize(submission.read_bytes()) == normalize(expected)
        return hashlib.sha256(first).hexdigest()
    finally:
        if original is None:
            submission.unlink(missing_ok=True)
        else:
            submission.write_bytes(original)


def check_observation_dependency(modules):
    mock = modules["mock_environment"]

    def run(mode):
        env, _ = mock.make_mock_env(seed=42)
        original = env.run_pilot

        def observed(*args, **kwargs):
            if mode == "error":
                raise RuntimeError("synthetic pilot failure")
            result = original(*args, **kwargs)
            if mode == "positive":
                result["observed_lift_ratio"] = abs(result["observed_lift_ratio"]) + 0.2
            elif mode == "negative":
                result["observed_lift_ratio"] = -abs(result["observed_lift_ratio"]) - 0.2
            env.pilot_history[-1]["observed_lift_ratio"] = result["observed_lift_ratio"]
            return result

        env.run_pilot = observed
        campaigns = modules["agent"].Agent().act(env)
        return campaigns

    positive = run("positive")
    negative = run("negative")
    run("error")
    assert positive != negative, "final decisions do not depend on pilot observations"
    return {"positive_campaigns": len(positive), "negative_campaigns": len(negative),
            "error_case": "completed"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="participant checkout to validate")
    args = parser.parse_args()
    repo, modules = load_target(args.repo)
    started = time.perf_counter()
    report = {
        "agent_version": hashlib.sha256((repo / "agent.py").read_bytes()).hexdigest(),
        "raw_agent": check_raw_agent(modules),
        "evaluator": check_evaluator(repo),
        "submission_sha256": check_reproducibility(repo, modules),
        "observation_dependency": check_observation_dependency(modules),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "status": "PASS",
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()