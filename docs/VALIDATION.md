# Independent validation record

## Scope and pinned input

This report uses the fetched target-branch base `61c118ba07c185ce835678caafa971dc09d84b82` (`feature/pilot-uncertainty-calibration`), preserving its retry and uncertainty-calibration work, with the pilot-error contingency change described below. The checked `agent.py` SHA-256 is `cdfecd36c3b4b3655b9c1fc9156406741ed1580abbd459928a74b2847c5b2e01`.

The requested captain checkout at `C:\AIKYN-HACKALEM\hack-30b4fd86-aikyn-build` was not present. The target branch was fetched and its existing retry/calibration changes were preserved; the results apply to that branch plus the pilot-error contingency in this change. The organizer-provided `local_eval.py`, `make_submission.py`, `environment.py`, `mock_environment.py`, `scoring_core.py`, and data were left unchanged.

## Reproduce from a clean environment

Run from the repository root. The virtual environment used for this report had Python 3.14.7, pandas 3.0.6, and numpy 2.5.3. `requirements.txt` pins pandas and numpy to those versions; uv also installed python-dateutil 2.9.0.post0, six 1.17.0, and tzdata 2026.4.

```powershell
python -m venv .venv-clean
.\.venv-clean\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONIOENCODING = 'utf-8'
.\.venv-clean\Scripts\python.exe local_eval.py
.\.venv-clean\Scripts\python.exe local_eval.py --runs 10
.\.venv-clean\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-clean\Scripts\python.exe -c "import sys; sys.path.insert(0, 'tests'); import test_agent_strategy as t; tests=[getattr(t,n) for n in dir(t) if n.startswith('test_')]; [f() for f in tests]; print(len(tests), 'strategy tests passed')"
.\.venv-clean\Scripts\python.exe verify_pass.py
```

On the validation machine, Windows reported `Windows-11-10.0.26200-SP0`. A fresh `.venv-clean` environment was created from Python 3.14.7 and installed the pinned requirements successfully; pip used cached wheels. The public case guide permits up to 10 minutes, and this agent's measured `Agent.act` times were 0.2232–0.2514 seconds across seeds 0–9, excluding environment setup and dependency installation.

The public files visible in this checkout do not specify the Python version or OS used by the remote judge. Python 3.14.7 with the pinned dependency versions is verified here; compatibility with an undocumented judge image cannot be asserted from these files.

## Results

| Check | Result |
|---|---|
| `local_eval.py`, seed 42 | PASS; net mock result +1,222,447; cost 31,488; contacts 7,872; 20 pilots + 5 final campaigns |
| `local_eval.py --runs 10` | PASS; 10/10 mock seeds positive; range +1,247,717 to +1,730,401; median +1,602,548 |
| Direct raw-output validation, seeds 0–9 | PASS; no sanitizer/cap applied; 4–7 final campaigns; 20 pilots per run |
| Independent budgets/reach, seeds 0–9 | PASS; total cost 23,056–46,260 of 100,000; total contacts 5,764–11,565 of 15,000, including pilot contacts |
| Per-campaign size and final overlap | PASS; every final segment was nonempty and at most 5,000; no final-final subscriber overlap |
| Campaign contract | PASS; required tariff/channel and supported filter values validated on raw output |
| Contract and strategy tests | PASS; 7 unittest cases and 6 strategy test functions cover noisy/negative observations, no history, observation dependence, limits, transient/persistent pilot failure, and refinement exhaustion |
| `make_submission.py`, run twice | PASS; CSVs match after CRLF/LF normalization; SHA-256 of LF-normalized seed-42 output: `6d3b71906eb7a21b451d2e174ccc0bac3d0f9af4d411194ed52c2f70d5c0eb2d` |
| Saved `submission.csv` vs current agent | PASS; matches the generated CSV after newline normalization |
| Changed pilot observations | PASS; for the same seed/profile and pilot sequence, controlled positive observations for tariff 9 versus tariff 8 changed the selected final choices |
| Secret/unrelated diff review | PASS; changes are confined to agent recovery, validation tests/docs, README and team status; no `.env`, keys, tokens, virtual environment or personal files are included |

`Кампаний: 25` in the seed-42 evaluator output counts the 20 pilots plus 5 final campaigns. The evaluator's displayed remaining budget and reach are pilot-stage balances; the totals above include both pilots and final campaigns. The positive values are results from the supplied mock model, not a prediction or guarantee of a hidden score.

`verify_pass.py` calls `Agent.act(env)` directly and validates its raw list before any call to `sanitize_campaigns`. It checks all ten seeds, independently sums pilot and final costs/contacts, enforces the 5-minute target, validates the campaign schema and segments, and checks final segment overlap. Pilot contact counts come from the actual explicit subscriber IDs; repeated pilot contacts still count again toward reach and cost.

The local evaluator catches exceptions raised out of `Agent.act` and may then exit successfully with a fallback empty plan. No such uncaught agent exception appeared in the two evaluator runs. Direct validation is the evidence for the raw contract and limits; exit code zero alone is not treated as a pass.

## Adversarial contract cases and handoff

`tests/test_contract.py` uses only the documented `env` fields and `run_pilot` method. It covers noisy and negative observations, an initially empty pilot history, constrained remaining resources, controlled changes to pilot observations, transient and persistent pilot API failures, and no remaining contact capacity.

The pilot recovery preserves the target branch's one retry when pilot counters remain unchanged, records exceptions in `agent.audit['pilot_errors']`, and continues to other hypotheses after a failed candidate. If no pilot returns usable observations, it selects one historical-prior contingency on the cheapest affordable channel, splitting with public filters to keep the segment within 5,000 contacts. The campaign and audit both label it as untested; this is a risk fallback, not a pilot-based decision. Tests confirm that the plan obeys reach and budget limits.

**Zero remaining contacts** remains an impossible input for the required nonempty plan: no pilot can run and no final contact can be made. A final campaign is also impossible if no channel/audience fits the remaining budget and reach; the agent returns `[]` rather than exceed limits.

The controlled-observation test holds the profile, seed, and candidates fixed. It returns `1.0` for a selected tariff and `0.0` for the others, then swaps the favored tested tariff. The final choices differ, showing the decisions consume pilot observations rather than only incrementing the call count. This is a synthetic contract test, not evidence about hidden environment outcomes.

The controlled-observation test holds the profile, seed, and candidates fixed. It returns `1.0` for a selected tariff and `0.0` for the others, then swaps the favored tested tariff. The final choices differ, showing the decisions consume pilot observations rather than only incrementing the call count. This is a synthetic contract test, not evidence about hidden environment outcomes.

## Short demo sequence

1. Start in a fresh checkout and install the pinned requirements.
2. Run `local_eval.py`; point out that the displayed 24 campaigns include 20 pilots and 4 finals.
3. Show the pilot log and the direct raw validator's independent cost/reach totals.
4. Run `make_submission.py`; show the CSV and its LF-normalized SHA-256.
5. Run `make_submission.py` again and compare the normalized output.
6. Run `local_eval.py --runs 10` and explain that this reports mock robustness only.

The submission file and final `validation.json` should be regenerated by the captain after integration with Nurlan's final `agent.py`; this report does not replace that integration check.
