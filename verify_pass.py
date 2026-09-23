"""Acceptance checks independent of evaluator's automatic sanitizing/capping."""
import hashlib
import json
import time
from pathlib import Path
import pandas as pd
from agent import Agent
from mock_environment import make_mock_env
from scoring_core import apply_filters, validate_strategy
from make_submission import build_submission


def main():
    started = time.perf_counter()
    checks = []
    for seed in range(10):
        env, _ = make_mock_env(seed=seed)
        agent = Agent()
        begin = time.perf_counter()
        campaigns = agent.act(env)
        elapsed = time.perf_counter() - begin
        assert elapsed < 300, (seed, elapsed)
        assert 1 <= len(campaigns) <= 10
        validate_strategy(pd.DataFrame(campaigns), env.tariffs)
        assert 0 < len(env.pilot_history) <= 20
        assert all(10 <= p['n_customers'] <= 200 for p in env.pilot_history)
        money = sum(p['cost'] for p in env.pilot_history)
        contacts = sum(p['n_customers'] for p in env.pilot_history)
        reached = set()
        for campaign in campaigns:
            frame = apply_filters(env.customer_profile, pd.Series(campaign))
            assert 0 < len(frame) <= 5000
            ids = set(frame.ID_NUMBER)
            assert not reached.intersection(ids), 'Final campaigns overlap'
            reached.update(ids)
            money += len(frame) * env.channels[campaign['channel']]['cost_per_contact']
            contacts += len(frame)
        assert money <= env.total_budget
        assert contacts <= env.max_total_contacts
        checks.append(dict(seed=seed, campaigns=len(campaigns), pilots=len(env.pilot_history),
                           total_cost=money, total_contacts=contacts, seconds=round(elapsed, 3)))
    first = build_submission(Agent()).to_csv(index=False, lineterminator='\n')
    second = build_submission(Agent()).to_csv(index=False, lineterminator='\n')
    assert first == second, 'Submission is not deterministic'
    assert Path('submission.csv').read_text(encoding='utf-8') == first
    report = dict(status='PASS', checks=checks, submission_reproducible=True,
                  submission_sha256=hashlib.sha256(first.encode()).hexdigest(),
                  total_seconds=round(time.perf_counter()-started, 3))
    Path('validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
