# AIKYN BILD validation

## Scope

`verify_pass.py` validates a participant checkout without modifying its agent or
organizer modules. It calls the raw `Agent.act(env)` result before
`sanitize_campaigns`, then separately runs the public evaluator and submission
builder. It does not inspect closures, hidden impact models, or organizer-only
state.

Run from the validation checkout:

```powershell
py -3 verify_pass.py --repo ..\published-main
```

For a different participant checkout, pass its absolute or relative path with
`--repo`. The checker changes into that checkout because the public mock uses
relative `data/` paths.

## Checks

The checker covers:

- raw output: 1-10 dictionaries, known tariffs/channels/filter values,
	non-empty filtered segments, and no more than 5,000 customers per campaign;
- all pilot and final contacts/costs together, including repeated pilot
	contacts, with limits of 20 pilots, 100,000 budget, and 15,000 contacts;
- no overlap between final campaign segments;
- `local_eval.py` and `local_eval.py --runs 10`, rejecting agent crashes and
	evaluator messages that indicate discarded campaigns;
- two `make_submission.py` runs with CRLF/LF normalization, plus equality with
	`build_submission(Agent())` from the current checkout;
- negative observations, synthetic pilot failure, and controlled positive vs
	negative observations. A difference in the final plans is required for the
	observation-dependency check.

The separate regression tests can be run with:

```powershell
$env:AIKYN_REPO = "..\published-main"
py -3 -m unittest tests.test_contract -v
```

## Recorded run

Checked checkout: `published-main` at the time of validation.

Environment:

- Windows host (OS edition not recorded), Python 3.14
- `pandas==3.0.6`
- `numpy==2.5.3`
- dependencies available from the participant `requirements.txt`
- no network service, API key, Docker, or SUN required

The checked `agent.py` SHA-256 was:

`592733697169cac47781fee94c4ecfcc5ec5fab8fb455fe64d3556f4c9f6b165`

Observed result from `verify_pass.py`:

- raw seeds 0-9: PASS; 3-7 final campaigns and 20 pilots per seed;
- combined totals: 5,119-12,965 contacts and 20,476-49,280 cost;
- `local_eval.py`: PASS in 1.059 s;
- `local_eval.py --runs 10`: PASS in 5.841 s;
- raw `Agent.act` time: 0.234-0.269 s per seed;
- submission SHA-256 after normalized comparison:
	`b7704e14de0340ce5d76bd8d2aff23315829d880fe85560fb101c62f073ac828`;
- positive/negative controlled observations produced 4 vs 1 campaigns;
- synthetic pilot failure completed without an exception escaping `Agent.act`.

## Risks and limits

These results validate the public mock mechanics, not the hidden judging model
or a future version of `agent.py`. The `--runs 10` net results are synthetic
and must not be presented as a score guarantee. A test environment with no
eligible customers or no affordable contacts is an impossible mandatory-pilot
case; it must be reported as an input-contract limitation, not converted into
a PASS. The final `submission.csv` and `validation.json` should be regenerated
after integrating any later agent change.

Before handoff, inspect only tracked files for accidental credentials or local
artifacts:

```powershell
git status --short
git diff --check
git diff -- . ':!submission.csv' ':!validation.json'
```
