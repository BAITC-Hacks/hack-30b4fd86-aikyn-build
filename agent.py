"""AIKYN BILD: history proposes hypotheses; public pilots drive decisions."""
from pathlib import Path
import math
import pandas as pd


PER_CUSTOMER_STD = 0.804


def _pilot_uncertainty(samples):
    return PER_CUSTOMER_STD / math.sqrt(samples)


class Agent:
    def _priors(self):
        path = Path(__file__).resolve().parent / 'data' / 'change_tariff.csv'
        try:
            history = pd.read_csv(path)
            before = history['AVG_ARPU_PREV_3M']
            history['arpu_segment'] = pd.cut(
                before, [-float('inf'), 1000, 5000, float('inf')],
                labels=['LOW', 'MID', 'HIGH'], right=False)
            history['ratio'] = ((history['AVG_ARPU_NEXT_3M'] - before)
                                / before.clip(lower=100)).clip(-1, 2)
            groups = history.groupby(['tariff_plan_code_from', 'arpu_segment',
                                      'tariff_plan_code_to'], observed=True)['ratio']
            return {key: float(values.median()) * len(values) / (len(values) + 20)
                    for key, values in groups}
        except (OSError, KeyError, ValueError):
            return {}

    def act(self, env):
        self.audit = {'pilots': [], 'campaigns': []}
        profile = env.customer_profile
        priors = self._priors()
        tariffs = sorted(env.tariffs['tariff_plan_code'].astype(str))
        candidates = []
        # Disjoint cells prevent final campaigns from competing for the same people.
        for (current, segment), frame in profile.groupby(
                ['current_tariff', 'arpu_segment'], observed=True, sort=True):
            if len(frame) < 10:
                continue
            choices = sorted((t for t in tariffs if t != current),
                             key=lambda t: (-priors.get((current, segment, t), 0), t))
            for target in choices[:2]:
                prior = priors.get((current, segment, target), 0)
                candidates.append(dict(current=str(current), segment=str(segment),
                                       target=target, prior=prior, frame=frame,
                                       priority=(max(prior, 0) + .05)
                                       * float(frame.predicted_arpu.sum()),
                                       samples=0, weighted=0., repeats=0,
                                       failed=False))
        candidates.sort(key=lambda c: (-c['priority'], c['current'], c['target']))
        channel = 'sms' if 'sms' in env.channels else min(
            env.channels, key=lambda k: env.channels[k]['cost_per_contact'])
        cost = env.channels[channel]['cost_per_contact']

        def pilot(candidate):
            count = min(200, len(candidate['frame']), int(env.remaining_contacts) - 10)
            if cost:
                count = min(count, int(env.remaining_budget // cost))
            if count < 10 or env.pilots_left <= 0:
                return False
            for attempt in range(2):
                counters = (env.remaining_budget, env.remaining_contacts,
                            env.pilots_left)
                try:
                    result = env.run_pilot(
                        target_tariff=candidate['target'], channel=channel,
                        n_customers=count,
                        filter_current_tariff=candidate['current'],
                        filter_arpu_segment=candidate['segment'])
                    break
                except (RuntimeError, ValueError) as error:
                    counters_changed = counters != (
                        env.remaining_budget, env.remaining_contacts, env.pilots_left)
                    self.audit.setdefault('pilot_errors', []).append({
                        'target_tariff': candidate['target'],
                        'attempt': attempt + 1,
                        'error': type(error).__name__,
                        'counters_changed': counters_changed,
                    })
                    if attempt == 0 and not counters_changed:
                        continue
                    candidate['failed'] = True
                    return False
            n, ratio = int(result['n_customers']), float(result['observed_lift_ratio'])
            if n > 0 and math.isfinite(ratio):
                candidate['samples'] += n
                candidate['weighted'] += n * ratio
                candidate['repeats'] += 1
            self.audit['pilots'].append(dict(result))
            return True

        # Explore several source cells before spending a second pilot on a cell.
        exploration, seen = [], set()
        for c in candidates:
            key = (c['current'], c['segment'])
            if key not in seen:
                exploration.append(c)
                seen.add(key)
        exploration += [c for c in candidates if not any(c is e for e in exploration)]
        explored = []
        for candidate in exploration[:12]:
            if pilot(candidate):
                explored.append(candidate)
        # Refine plausible winners; uncertainty is a conservative heuristic,
        # not a calibrated guarantee for the hidden population.
        while explored and env.pilots_left > 0:
            eligible = [c for c in explored if c['samples'] and c['repeats'] < 3
                        and not c['failed']]
            if not eligible:
                break
            def opportunity(c):
                mean = c['weighted'] / c['samples']
                uncertainty = _pilot_uncertainty(c['samples'])
                return (mean + uncertainty) * float(c['frame'].predicted_arpu.sum())
            plausible = [c for c in eligible if opportunity(c) > 0]
            if not plausible:
                break
            fewest_repeats = min(c['repeats'] for c in plausible)
            candidate = max((c for c in plausible
                             if c['repeats'] == fewest_repeats), key=opportunity)
            if not pilot(candidate) and not candidate['failed']:
                break

        if not self.audit['pilots']:
            self.audit['refusal'] = 'No successful pilots; campaign plan withheld.'
            return []

        options = []
        for c in explored:
            if not c['samples']:
                continue
            mean = c['weighted'] / c['samples']
            lower = mean - 1.28 * _pilot_uncertainty(c['samples'])
            frame = c['frame']
            # Split large cells using supported filters rather than relying on truncation.
            parts = [(None, None, frame)] if len(frame) <= 5000 else [
                (str(data), str(call), part) for (data, call), part in frame.groupby(
                    ['data_segment', 'call_segment'], observed=True, sort=True)]
            for data, call, part in parts:
                if not 0 < len(part) <= 5000:
                    continue
                # Only extrapolate down from the measured channel: avoids assuming
                # that expensive channels scale linearly beyond conversion saturation.
                for name, spec in env.channels.items():
                    scale = spec['conversion_multiplier'] / env.channels[channel]['conversion_multiplier']
                    if scale > 1:
                        continue
                    money = len(part) * spec['cost_per_contact']
                    value = lower * scale * float(part.predicted_arpu.sum()) - money
                    campaign = dict(filter_current_tariff=c['current'],
                                    filter_arpu_segment=c['segment'],
                                    target_tariff=c['target'], channel=name)
                    if data is not None:
                        campaign.update(filter_data_segment=data, filter_call_segment=call)
                    options.append((value, money, len(part),
                                    (c['current'], c['segment'], data, call), campaign,
                                    mean, lower))
        options.sort(key=lambda o: (-o[0], o[1], str(o[3]), o[4]['target_tariff']))
        budget, contacts = env.remaining_budget, env.remaining_contacts
        selected, used = [], set()
        for value, money, count, key, campaign, mean, lower in options:
            if value <= 0 or key in used or money > budget or count > contacts:
                continue
            campaign['campaign_name'] = f'AIKYN_BILD_{len(selected)+1:02d}'
            selected.append(campaign)
            used.add(key)
            budget -= money
            contacts -= count
            self.audit['campaigns'].append(dict(campaign=campaign.copy(), contacts=count,
                                                cost=money, pilot_mean=mean,
                                                conservative_ratio=lower, estimated_net=value))
            if len(selected) == 10:
                break
        # The contract requires a nonempty plan even after an unlucky exploration.
        # Return the smallest affordable tested cell on the free channel; flag risk.
        if not selected:
            fallback = [o for o in options if o[1] == 0 and o[2] <= contacts]
            if fallback:
                best = max(fallback, key=lambda o: o[0])
                campaign = best[4].copy()
                campaign['campaign_name'] = 'AIKYN_BILD_fallback_risk'
                selected.append(campaign)
                self.audit['fallback'] = 'No conservative positive option; best tested free option.'
        return selected
