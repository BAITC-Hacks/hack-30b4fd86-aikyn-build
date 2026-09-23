# Independent validation record

## Scope and pinned input

This report checks the working tree at commit `56d72608808b630a21f5103ac71edb1c13ef30b8` (`origin/main` in the available checkout). The checked `agent.py` SHA-256 is `592733697169cac47781fee94c4ecfcc5ec5fab8fb455fe64d3556f4c9f6b165`. The commit and file hash pin the exact strategy used below.

The requested captain checkout at `C:\AIKYN-HACKALEM\hack-30b4fd86-aikyn-build` was not present. The available checkout is later/different from the handoff baseline described as `3260bb9`: its `origin/main` is `56d7260` and includes `agent.py`. Results below therefore apply to this available pinned version; they do not establish the captain's baseline state. The organizer-provided `local_eval.py`, `make_submission.py`, `environment.py`, `mock_environment.py`, `scoring_core.py`, and data were left unchanged.

## Reproduce from a clean environment

Run from the repository root. The virtual environment used for this report had Python 3.14.7, pandas 3.0.6, and numpy 2.5.3. `requirements.txt` pins pandas and numpy to those versions; uv also installed python-dateutil 2.9.0.post0, six 1.17.0, and tzdata 2026.4.

```powershell
uv venv .venv --python 3.14
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe local_eval.py
.\.venv\Scripts\python.exe local_eval.py --runs 10
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe verify_pass.py
```

On the validation machine, Windows reported `Windows-11-10.0.26200-SP0`. The `python` and `py` launchers were not on PATH, so commands used the virtual-environment interpreter explicitly. The public case guide permits up to 10 minutes, and this agent's measured `Agent.act` times were 0.2193–0.2381 seconds across seeds 0–9, excluding environment setup and dependency installation.

The public files visible in this checkout do not specify the Python version or OS used by the remote judge. Python 3.14.7 with the pinned dependency versions is verified here; compatibility with an undocumented judge image cannot be asserted from these files.

## Results

| Check | Result |
|---|---|
| `local_eval.py`, seed 42 | PASS; net mock result +1,184,176; cost 23,056; contacts 5,764; 20 pilots + 4 final campaigns |
| `local_eval.py --runs 10` | PASS; 10/10 mock seeds positive; range +1,185,097 to +1,824,165 |
| Direct raw-output validation, seeds 0–9 | PASS; no sanitizer/cap applied; 3–7 final campaigns; 20 pilots per run |
| Independent budgets/reach, seeds 0–9 | PASS; total cost 20,476–49,280 of 100,000; total contacts 5,119–12,965 of 15,000, including pilot contacts |
| Per-campaign size and final overlap | PASS; every final segment was nonempty and at most 5,000; no final-final subscriber overlap |
| Campaign contract | PASS; required tariff/channel and supported filter values validated on raw output |
| Contract tests | PASS for noise, negative observations, no history, changed-observation dependence, and constrained balances; FAIL for a pilot error before any successful observation (empty final plan); N/A for zero-contact capacity because the required pilot cannot run |
| `make_submission.py`, run twice | PASS; CSVs match after normalizing CRLF/LF; SHA-256 of LF-normalized output: `b7704e14de0340ce5d76bd8d2aff23315829d880fe85560fb101c62f073ac828` |
| Saved `submission.csv` vs current agent | PASS; matches the generated CSV after newline normalization |
| Changed pilot observations | PASS; for the same seed/profile and pilot sequence, controlled positive observations for tariff 9 versus tariff 8 changed the selected final choices |
| Secret/unrelated diff review | PASS; patch contains only `verify_pass.py`, `tests/test_contract.py`, and this report; no `.env`, virtual environment, keys, tokens, or personal files are included |

`Кампаний: 24` in the seed-42 evaluator output counts the 20 pilots plus 4 final campaigns. The evaluator's displayed remaining budget and reach are pilot-stage balances; the totals above include both pilots and final campaigns. The positive values are results from the supplied mock model, not a prediction or guarantee of a hidden score.

`verify_pass.py` calls `Agent.act(env)` directly and validates its raw list before any call to `sanitize_campaigns`. It checks all ten seeds, independently sums pilot and final costs/contacts, enforces the 5-minute target, validates the campaign schema and segments, and checks final segment overlap. Pilot contact counts come from the actual explicit subscriber IDs; repeated pilot contacts still count again toward reach and cost.

The local evaluator catches exceptions raised out of `Agent.act` and may then exit successfully with a fallback empty plan. No such uncaught agent exception appeared in the two evaluator runs. Direct validation is the evidence for the raw contract and limits; exit code zero alone is not treated as a pass.

## Adversarial contract cases and handoff

`tests/test_contract.py` uses only the documented `env` fields and `run_pilot` method. It covers noisy and negative observations, an initially empty pilot history, constrained remaining resources, controlled changes to pilot observations, pilot API exceptions, and no remaining contact capacity.

Two cases identify constraints the current agent cannot satisfy:

1. **Every pilot call raises.** Reproducer: `env, _ = make_mock_env(seed=42)`; replace `env.run_pilot` with a function that raises `RuntimeError`; then call `Agent().act(env)`. The agent catches the first error, stops exploration, and returns `[]`. This violates the 1-campaign minimum. It also means the evaluator's exception handler does not expose the underlying pilot error, because the agent absorbs it.
2. **Zero remaining contacts before `act`.** Reproducer: create the same environment, set `env.remaining_contacts = 0`, then call `Agent().act(env)`. No pilot can be launched and the agent returns `[]`. Requiring at least one pilot and at least one final campaign is impossible with zero available contacts; this is a contradictory input, not a feasible PASS case.

These reproducible agent findings should go to Nurlan for strategy handling. `agent.py` was not modified in this validation patch. Pilot exceptions are caught, so the agent process does not crash, but the current loop stops exploration on the first failed call; a failure before any successful observation produces the empty-plan gap above.

The controlled-observation test holds the profile, seed, and candidates fixed. It returns `1.0` for a selected tariff and `0.0` for the others, then swaps the favored tested tariff. The final choices differ, showing the decisions consume pilot observations rather than only incrementing the call count. This is a synthetic contract test, not evidence about hidden environment outcomes.

## Short demo sequence

1. Start in a fresh checkout and install the pinned requirements.
2. Run `local_eval.py`; point out that the displayed 24 campaigns include 20 pilots and 4 finals.
3. Show the pilot log and the direct raw validator's independent cost/reach totals.
4. Run `make_submission.py`; show the CSV and its LF-normalized SHA-256.
5. Run `make_submission.py` again and compare the normalized output.
6. Run `local_eval.py --runs 10` and explain that this reports mock robustness only.

The submission file and final `validation.json` should be regenerated by the captain after integration with Nurlan's final `agent.py`; this report does not replace that integration check.
