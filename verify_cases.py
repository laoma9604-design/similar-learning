"""Recompute the explanatory cases used in the taskbook (stdlib only)."""
import csv
import json
import math
from itertools import permutations
from pathlib import Path

OUT = Path(__file__).resolve().parent


def source(n, rate, quadratic=False):
    return (n * n / 1000 if quadratic else n) * (1 + rate)


def target(principal, rate):
    return principal * (1 + rate)


def error(rs, rt):
    return min(1.0, (rs - rt) ** 2)


def bump(u):
    return .3 * (math.exp(-((u - .13) / .03) ** 2)
                 - math.exp(-(.13 / .03) ** 2))


def main():
    source_order = ['N_t', 'rate_s', 'N_next']
    target_order = ['A_next', 'A_t', 'rate_t']
    mapping = {'N_t': 'A_t', 'rate_s': 'rate_t', 'N_next': 'A_next'}
    source_roles = {'N_t': 'current', 'rate_s': 'ratio', 'N_next': 'next'}
    target_roles = {'A_t': 'current', 'rate_t': 'ratio', 'A_next': 'next'}
    assert [target_order.index(mapping[node]) for node in source_order] == [1, 2, 0]
    assert all(source_roles[node] == target_roles[mapping[node]] for node in source_order)
    swapped = {'N_t': 'rate_t', 'rate_s': 'A_t', 'N_next': 'A_next'}
    assert set(swapped.values()) == set(target_order)
    assert {swapped[node] for node in source_order[:2]} == {'A_t', 'rate_t'}
    assert sum(source_roles[node] != target_roles[swapped[node]] for node in source_order) == 2
    laplacian = [[(1.0 if i == j else 0.0) - 1 / 3 for j in range(3)] for i in range(3)]
    for eigenvalue, vector in [(0, [1, 1, 1]), (1, [1, -1, 0]), (1, [1, 1, -2])]:
        result = [sum(a * b for a, b in zip(row, vector)) for row in laplacian]
        assert all(math.isclose(a, eigenvalue * b, abs_tol=1e-12) for a, b in zip(result, vector))

    kernel = [[9.0, 8.0], [8.0, 1.0]]
    for _ in range(30):
        kernel = [[value / sum(row) for value in row] for row in kernel]
        columns = [sum(row[j] for row in kernel) for j in range(2)]
        kernel = [[value / columns[j] for j, value in enumerate(row)] for row in kernel]
    expected = [[3 / 11, 8 / 11], [8 / 11, 3 / 11]]
    assert all(math.isclose(kernel[i][j], expected[i][j], abs_tol=1e-12)
               for i in range(2) for j in range(2))
    weights = [[.40, .35, .25], [.40, .30, .30], [.20, .35, .45]]
    assignments = list(permutations(range(3)))
    best = max(assignments, key=lambda perm: sum(weights[i][j] for i, j in enumerate(perm)))
    assert best == (1, 0, 2)
    assert math.isclose(sum(weights[i][j] for i, j in enumerate(best)), 1.20)
    assert math.isclose(sum(weights[i][i] for i in range(3)), 1.15)
    scores = [sum(math.log(weights[i][j]) for i, j in enumerate(perm)) / 3
              for perm in [best, (0, 1, 2)]]
    assert math.isclose(scores[0], -.9215401842, abs_tol=1e-10)
    assert math.isclose(scores[1], -.9729237441, abs_tol=1e-10)
    assert scores[0] > scores[1]
    costs = [[1 - value for value in row] for row in weights]
    reduced = [[value - min(row) for value in row] for row in costs]
    minima = [min(row[j] for row in reduced) for j in range(3)]
    reduced = [[value - minima[j] for j, value in enumerate(row)] for row in reduced]
    assert all(math.isclose(reduced[i][j], 0, abs_tol=1e-12) for i, j in enumerate(best))
    pairs = [(.2, .1), (-.2, -.1), (0, 0), (.003, -.003), (.2, .2), (-.2, .2)]
    directions = [((rs > .01) - (rs < -.01), (rt > .01) - (rt < -.01)) for rs, rt in pairs]
    assert sum(ds == dt for ds, dt in directions) / len(pairs) == 5 / 6
    assert math.isclose((error(.2, 0) + error(2, 0)) / 2, .52)
    assert math.isclose((error(.2, 0) + error(-.2, 0)) / 2, .04)
    assert math.isclose(error(-.01, .01), .0004)
    assert sum([.001, .002, .08]) / 3 < .05 < max([.001, .002, .08])

    role_directions = {'current': '-', 'ratio': '-', 'next': '+'}
    structural_losses = []
    for candidate in [mapping, swapped]:
        permutation = [[int(candidate[src] == tgt) for tgt in target_order] for src in source_order]
        squared_difference = 0
        for role, expected_direction in role_directions.items():
            for direction in ['-', '+']:
                hs = [int(source_roles[node] == role and direction == expected_direction) for node in source_order]
                ht = [int(target_roles[node] == role and direction == expected_direction) for node in target_order]
                aligned = [sum(weight * value for weight, value in zip(row, ht)) for row in permutation]
                squared_difference += sum((a - b) ** 2 for a, b in zip(hs, aligned))
        structural_losses.append(squared_difference / (2 * len(role_directions) * 3 * 1))
    assert structural_losses[0] == 0
    assert math.isclose(structural_losses[1], 2 / 9)

    def weighted_risk(scores, risks, temperature=1.0):
        weights = [math.exp((score - max(scores)) / temperature) for score in scores]
        total = sum(weights)
        weights = [weight / total for weight in weights]
        return weights, sum(weight * risk for weight, risk in zip(weights, risks))

    risks = [.02, .50]
    _, risk_before = weighted_risk([-1, -1], risks)
    assert math.isclose(risk_before, .26)
    weights, risk_tilted = weighted_risk([-1, -1 - math.log(3)], risks)
    assert math.isclose(weights[0], .75) and math.isclose(risk_tilted, .14)
    for scores, temperature in [([-1, -1], 1.0), ([-.4, -1.1], .5)]:
        weights, loss = weighted_risk(scores, risks, temperature)
        for i in range(2):
            step = 1e-6
            plus, minus = scores.copy(), scores.copy()
            plus[i] += step
            minus[i] -= step
            numerical = (weighted_risk(plus, risks, temperature)[1]
                         - weighted_risk(minus, risks, temperature)[1]) / (2 * step)
            analytic = weights[i] * (risks[i] - loss) / temperature
            assert math.isclose(analytic, numerical, abs_tol=1e-9)
    gradients = [.5 * (risk - risk_before) for risk in risks]
    assert all(math.isclose(a, b) for a, b in zip(gradients, [-.12, .12]))
    updated = [-1 - .1 * gradient for gradient in gradients]
    weights, risk_after = weighted_risk(updated, risks)
    assert all(math.isclose(a, b) for a, b in zip(updated, [-.988, -1.012]))
    assert math.isclose(weights[0], .506, abs_tol=1e-6)
    assert math.isclose(risk_after, .2571, abs_tol=5e-5) and risk_after < risk_before
    for scores, equal_risks in [([-1], [.02]), ([-.4, -1.1], [.2, .2])]:
        weights, loss = weighted_risk(scores, equal_risks)
        assert all(math.isclose(weight * (risk - loss), 0, abs_tol=1e-12)
                   for weight, risk in zip(weights, equal_risks))

    records = []
    for u_n, u_r in [(0, 0), (.1, 0), (0, .2), (.1, .2), (.2, 0)]:
        ns = source(1000 * (1 + u_n), .1 * (1 + u_r))
        at = target(5000 * (1 + u_n), .1 * (1 + u_r))
        rs, rt = (ns - 1100) / 1100, (at - 5500) / 5500
        assert math.isclose(rs, rt, abs_tol=1e-12)
        records.append(dict(case='valid',u_n=u_n,u_r=u_r,source_out=ns,
                            target_out=at,r_source=rs,r_target=rt,error=error(rs,rt)))
    for u in [-.2, -.1, 0, .1, .2]:
        ns = source(1000 * (1 + u), .1, quadratic=True)
        at = target(5000 * (1 + u), .1)
        rs, rt = (ns - 1100) / 1100, (at - 5500) / 5500
        assert (rs > 0)-(rs < 0) == (rt > 0)-(rt < 0)
        records.append(dict(case='quadratic',u_n=u,u_r=0,source_out=ns,
                            target_out=at,r_source=rs,r_target=rt,error=error(rs,rt)))
    assert math.isclose(records[-1]['error'],.0576,abs_tol=1e-12)
    sparse = [-.2,-.1,0,.1,.2]
    sparse_max = max(bump(u)**2 for u in sparse)
    witness_error = bump(.13)**2
    assert sparse_max < .05 < witness_error
    assert math.isclose(source(1000,.11),1110,abs_tol=1e-9)
    with (OUT/'case-values.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    fixtures = dict(
        purpose='Development verification examples; excluded from formal test data.',
        target=dict(id='bank',nodes=['A_t','rate_t','A_next'],baseline=[5000,.1],
                    input_scales=[5000,.1],baseline_output=5500,output_scale=5500),
        sources=[dict(id='growth',nodes=['N_t','rate_s','N_next'],
                      baseline=[1000,.1],input_scales=[1000,.1],
                      baseline_output=1100,output_scale=1100,
                      function='N_t * (1 + rate_s)'),
                 dict(id='synthetic_square',nodes=['N_t','rate_s','N_next'],
                      baseline=[1000,.1],input_scales=[1000,.1],
                      baseline_output=1100,output_scale=1100,
                      function='N_t**2 / 1000 * (1 + rate_s)')],
        forward_map={'N_t':'A_t','rate_s':'rate_t','N_next':'A_next'},
        edge_map={'growth_relation':'interest_relation'},
        reversed_role_map={'N_t':'rate_t','rate_s':'A_t','N_next':'A_next'},
        example_thresholds=dict(gamma=.95,zeta=.05),
        local_error=dict(sparse_points=sparse,sparse_max=sparse_max,
                         witness_u=.13,witness_error=witness_error))
    (OUT/'case-fixtures.json').write_text(json.dumps(fixtures,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Checks passed; positive response at joint input = {records[3]["r_source"]:.4f}')
    print(f'Quadratic error = {records[-1]["error"]:.4f}')
    print(f'Local counterexample: sparse max {sparse_max:.6f}; witness {witness_error:.6f}')
    print('Structure checks passed: index map [1, 2, 0]; swapped roles fail twice; spectrum [0, 1, 1]')
    print('Matching and metric checks passed: Sinkhorn; assignment optimum; log scores; CTC; clipped error; maximum risk')
    print('Training checks passed: aligned structure loss 0 vs 2/9; softmax risk; finite-difference gradients; one score update; zero-gradient cases')


if __name__ == '__main__':
    main()
