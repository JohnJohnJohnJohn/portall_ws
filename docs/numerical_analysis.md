# DeskPricer Numerical Analysis — Models, Accuracy, Edge Cases

**Scope**: full numerical characterization of the pricing models as implemented in v3.5.0+unreleased (post-audit commits `de4f949`/`0a94821` plus the 2026-10-13 remediation). All numbers below were measured against the shipping code, not estimated. Reference oracles: an independent scipy BSM implementation (`tests/_bsm_ref.py`), QuantLib's `AnalyticEuropeanEngine`, QuantLib's `FdBlackScholesVanillaEngine` (independent of the binomial), and high-step CRR self-convergence.

**Analysis rounds**: round 1 (2026-10-12) — core accuracy, convergence, IV conditioning, PnL scaling, calendar effects. Round 2 (2026-10-13) — JR engine, bump-size sensitivity, reroute Greek consistency, American PnL, verify_reprice behavior, negative-rate/carry corners, warning-threshold sweeps, 0-DTE floor quantification.

---

## 1. Model inventory

| Path | Model | Role |
|------|-------|------|
| `pricing/bsm_fast.py` | Closed-form Black-Scholes-Merton (stdlib `math.erf`) | All European pricing; Americans rerouted when early exercise is provably valueless |
| `pricing/american.py` | QuantLib CRR/JR binomial lattice, bump-and-revalue Greeks | All other Americans |
| `pricing/implied_vol.py` | QuantLib Brent implied-vol solver (analytic or binomial objective) | IV inversion |
| `pricing/cross_greeks.py` | 4-point finite differences on the NPV path | vanna/volga |
| `pricing/engine.py` | Dispatch, adaptive steps, reroute logic | — |

**Conventions** (verified in code and tests): vega/rho per 1% point; theta/charm per calendar day (1-day revalue, forward-looking, negative for long options — sign opposite to Bloomberg display); all outputs per unit (qty=1); T floored to 1 day; ACT/365F; expiry quantized to whole calendar days with `Following` roll; default calendar Hong Kong.

---

## 2. Measured accuracy

### 2.1 European closed form — machine precision at matched T

Grid: 7 moneyness × 5 vols (5%–300%) × 5 maturities (1 day–50 yr) × call/put = 350 points, vs the scipy oracle at the *effective whole-day* T:

| Greek | Max abs error |
|-------|---------------|
| price | 2.8e-14 |
| delta | 1.6e-16 |
| gamma | 1.4e-17 |
| vega | 2.2e-16 |

The `math.erf` CDF is exact to double precision. **Any observed European "error" is a convention difference, not formula error** (see §4.1–4.2). Deep-ITM precision re-verified after the round-2 misdiagnosis correction: with the day-grid T matched, prices sit on the discounted lower bound to ~1e-10 (the CDF saturates exactly beyond |d₁|≈8.5; pinned by `TestDeepItmClosedFormPrecision`).

### 2.2 American binomial (CRR) — O(1/N) convergence, verified against an independent FD solver

ATM put (S=100, K=100, r=5%, q=1%, σ=20%, T=0.5), error vs CRR N=4000:

| N | price err | delta err | vega err |
|---|-----------|-----------|----------|
| 100 | −6.9e-3 | −7.7e-4 | −4.3e-4 |
| 250 | −2.6e-3 | +1.7e-4 | −1.9e-4 |
| 500 | −1.2e-3 | +2.4e-4 | −8.8e-5 |
| 1000 | −5.1e-4 | −9.3e-5 | −3.7e-5 |
| 2000 | −1.7e-4 | +4.3e-5 | −1.2e-5 |

Cross-check against `FdBlackScholesVanillaEngine` at fine resolution: FD(4000×2000) = 4.81801 vs CRR Richardson extrapolation 4.81807 — **agreement 6e-5**. (At coarse FD grids the FD engine itself is up to 1.1e-2 off; the binomial, not the FD reference, is the more converged method here.)

**Gamma is the weakest-converging Greek**: at ATM/moderate vol the second difference carries a persistent ≈ +1.3e-3 bias (≈ 5% relative) across N=100–2000, only shrinking at N≥4000. At σ=90% with N=150 the widened-bump gamma reads 0.0095 vs 0.0079 at N=2000 — **20% discrepancy**. See §2.7 for the bump-size dimension of the same issue. Rule of thumb: gamma from trees is good to one significant digit unless steps are high; request `steps≥2000` for gamma-sensitive work.

**Richardson extrapolation on theta/charm works for CRR**: at N=1000, theta error to the N=4000 truth improves 7.0e-7 → 1.3e-7 (5.6×). CRR theta is stable to 7 significant digits by N=500.

### 2.3 JR engine — price converges; theta/charm do not

Measured on the §2.2 benchmark: JR converges *from above* (N=250: +5.3e-3, N=1000: +1.0e-4 — faster than CRR at matched N for price). But **theta/charm oscillate without settling**: JR theta across N = 500/1000/2000/4000 reads −0.00903/−0.01377/−0.01023/−0.01153 vs CRR's stable −0.011073 (±20% swings; charm flips sign repeatedly). Root cause: the Richardson extrapolation is tuned for CRR's smooth O(1/N) error; JR's error is oscillatory and extrapolation amplifies rather than cancels. Gamma differs 11% from CRR at N=2000. **Guidance: `binomial_jr` is fine for price/vega/delta; do not trust its theta/charm/gamma.** JR's one structural advantage (register #20): valid where CRR throws negative-probability at very low vol.

### 2.4 Early-exercise behavior — correct pin and boundary

Deep-ITM pin (r=3%, q=0, T=0.25, σ=20%): at K/S=1.25 the American put prices at *exactly* intrinsic (25.000000), delta −1, vega 0 — immediate exercise. At K/S=1.11 it retains time value (11.485 vs 11.111 intrinsic, delta −0.86). Early-exercise premium grows smoothly with ITM-ness (e.g. put at r=5%: +0.19 ATM → +2.06 at K/S=1.25 → pinned beyond).

### 2.5 Reroute consistency — validated on all seven Greeks

The American→European reroute was re-verified at the Greek level (round 2): for a q+b≤0 call, the rerouted `bsm_fast` output and a N=4000 CRR tree agree to ≤ 7e-10 on price, delta, gamma, vega, **theta, rho and charm** — the calendar-day conventions are exactly aligned across both paths, not just the price.

### 2.6 Implied volatility

Round-trip (price at v₀ with the model, then invert), European analytic:

| case | IV error |
|------|----------|
| m=1.0, v₀=20% | +3.7e-9 |
| m=0.6, v₀=80% | +1.5e-8 |
| m=0.85, v₀=40% | −4.3e-6 |
| m=1.2, v₀=15% | −1.7e-5 |
| m=1.5, v₀=5% | **+2.8e-2 (2.8 vol-points!)** |

The last row is not a solver failure — see §4.4 (conditioning). American tree round-trip: 1.7–2.8e-4 across steps 500–3000. `verify_reprice` false-rejection risk measured at zero across 24 low-step American solves (min steps=10): the hybrid tolerance (50×accuracy, floored at 0.1% of target) is generous enough to absorb tree noise everywhere probed.

### 2.7 Bump-size sensitivity (American, N=4000)

Varying `bump_spot_rel`: delta stable to ~1e-4 over [0.001, 0.02], drifts −3.8e-3 at 0.05 (FD truncation). Gamma is **bimodal in bump size**: bumps ≤0.005 engage the sub-tick widening (h≈0.67, gamma ≈ 0.0324) while the default 0.01 runs the fine path (h=1.0, gamma ≈ 0.0308) and larger bumps truncate toward 0.0300 — a ≈7–8% total spread that is lattice geometry, not model disagreement. Vol bump insensitivity is excellent: vega/theta change <2e-5 across `bump_vol_abs` ∈ [0.0005, 0.01]. Conclusion: the default bumps are well chosen for delta/vega/theta; gamma inherits the §2.2 caveat regardless of bump.

### 2.8 PnL attribution residual scaling

European call (round 1, 1 day, backward): −0.2% of PnL on 1% moves, −1.4% on 5%, −4.7% on 10% spot+5 vol-pts, −15% on 20%+10pts. Cross-greeks changed large-move residuals by <0.5pt of PnL (residuals are third-order *spot* terms).

American put (round 2, N=2000, adverse spot moves): +2.5% (1% move), +4.8% (5%), **+14.5% (10%)** — larger *relative* residuals than the European case because the actual PnL shrinks against the move direction for a long put; `method=average` improves the 10% case to +12.7%. Absolute residuals stay ≤ 0.23 on a ~100-spot underlying. Expected use: daily marking, modest moves.

### 2.9 Cross-greeks

European vanna/volga vs analytic: |err| ≤ 2e-5 (≤ ~0.5% relative). **American volga at low steps is unreliable**: at N=500 volga reads −0.119 vs −0.000027 at N=2000 (4000× off — lattice noise). American vanna is stable. A warning is logged below 2000 steps (register #15).

### 2.10 Timing (timeout relevance)

Full Greeks at N=5000: **0.86 s per leg** (N=1000: 0.12 s). A 500-leg American book at 5000 steps ≈ 7 min in one worker task vs the 60 s default timeout → `503 PRICING_TIMEOUT` (documented in docs/api.md).

---

## 3. Strengths

1. **European path is exact** — machine-precision closed form; no discretization, no engine state.
2. **Two independent engines agree** — binomial (Richardson-extrapolated) and finite-difference cross-validate to 6e-5 on Americans.
3. **Reroute is validated at Greek level** — all seven outputs match a high-step tree to ≤7e-10 including the calendar-day theta/charm conventions (§2.5); provably correct Merton conditions.
4. **Honest failure modes** — no-arb pre-checks (T-grid-aligned, American-intrinsic-aware), solver-bound errors, reprice verification (measured zero false rejections), non-finite guards, ill-conditioning and lattice-noise warnings.
5. **Consistent, documented conventions** — per-unit outputs, calendar-day theta, 1% Greeks, verified by 328 tests including property and golden fixtures.
6. **Well-chosen numerical defaults** — adaptive steps keep American price error ≲2e-3 at ~10× lower cost; bump defaults validated insensitive for delta/vega/theta (§2.7); CRR Richardson demonstrably effective.

---

## 4. Weaknesses, limits, and root causes

### 4.1 T is quantized to whole calendar days — price is a step function of `t`

`expiry_from_t` rounds `t·365` to the nearest whole day (floor 1). Consequences, measured:

- **Granularity step**: an ATM σ=60% option at t=1.5d reprices from 0.63 to 0.89 as t crosses the rounding boundary — a **0.26 jump (~42%)**.
- **0-DTE floor**: for true intraday t the 1-day floor *adds* value: ATM σ=30% call, floor(1d) = 0.632 vs true 0.36 at t=8h, 0.13 at t=1h, ~0 at t=0. Sub-day decay is invisible to the model — callers must supply live spot/IV that already reflects it (documented 0-DTE workflow).
- **Friday expiry roll**: t=1/365 on a Friday prices at 3 calendar days on all four business calendars (HK/NYSE/US-settlement/UK measured identical); ATM σ=30% 1-day call gains +0.46 (**+74%**). The >20% discrepancy warning fires.
- A caller passing t at a different day-count than ACT/365 silently lands on a different expiry.

### 4.2 Theta/charm are day-revalue conventions, not analytic derivatives

The 1-day revalue theta differs from analytic θ/365 by +3e-5…+1.4e-4/day (second-order/day-grid effects — both "correct" under their definitions). In the ≤1.5-day band theta is `intrinsic − price`, charm 0 — consistent but convention-discontinuous across the band edge.

### 4.3 Deep-ITM closed-form precision — corrected on re-measurement

**Original diagnosis (wrong)**: "cancellation below the lower bound" at d₁ ≥ +10, with ITM-via-parity proposed. **Re-measurement**: the deviation was the probe comparing day-grid prices against raw-`t` bounds. The corrected fact: beyond |d₁| ≈ 8.5 the double-precision CDF saturates exactly, the two large terms cancel *exactly*, and the price equals the discounted forward to ~1e-10. A parity prototype measured as a no-op and was removed. Deep-ITM BSM in double precision is well conditioned.

### 4.4 IV inversion conditioning collapses deep-ITM (fundamental, not a bug)

dIV/dPrice = 1/vega. Measured (put, T=0.225, σ=20%): K/S=1.0 → one cent of price error = 0.05 vol-points; K/S=1.25 → 0.7; **K/S=1.41 → 26; K/S=1.67 → 6.4e4**. Demonstrated: 3 cents of price span solved to IVs 29.0%/26.1%/22.0% with zero reprice residual. Deep-ITM IVs carry no vol information regardless of solver quality. Mitigations in place: structured `ill-conditioned` warning (vega < 0.01/1pt) and the api.md caveat. **Threshold note (round 2)**: the warning also fires on legitimately-quoted short-dated OTM options (measured: 10–15% OTM puts, σ≤20%, T=0.1) whose vega genuinely sits at ~0.008–0.01 — the flag means "ill-conditioned", not "garbage data"; tune to 0.005 if it proves noisy in practice.

### 4.5 Tree Greeks at low steps

Gamma bias ≈5% at moderate N and bump-dependent (§2.2, §2.7); American volga noise at N<2000 (§2.9); **JR theta/charm unreliable at all step counts** (§2.3). Mitigation is `steps` (and engine choice), at linear cost.

### 4.6 Known soft spots (documented, accepted)

- PnL attribution is a second-order Taylor product; relative residuals grow on adverse moves / large jumps (§2.8).
- Portfolio aggregate is a linear sum across possibly-divergent underlyings (warns at >5%).
- 500 American legs at high steps exceed the 60s worker timeout (§2.10).

---

## 5. Edge-case & failure register

Historical bugs (fixed) are marked ✦; round-2 findings are marked ●.

| # | Condition | Behavior | Status |
|---|-----------|----------|--------|
| 1 | t ∈ (1, 1.5]/365 and valuation+1 is a business day | Was: `ZeroDivisionError` → 500. Now: intrinsic-theta fallback | ✦ fixed |
| 2 | American put, r≈0, q+b<0 | Was: rerouted to European, underpriced ~1.4%. Now: tree | ✦ fixed |
| 3 | Empty optional query params (`b=`, `valuation_date=` …) | Was: 422. Now: defaults apply | ✦ fixed |
| 4 | Price below American intrinsic but above discounted European floor (HKEX settlement family) | Clean 400 naming the intrinsic bound ("lower bound 23.200000") | fixed (diagnosis); labeled European fallback on hold |
| 5 | Deep-ITM target in the raw-t vs day-grid T gap | Was: generic "outside solver bounds". Now: informative lower-bound message (pre-check discounts at day-grid T) | ✦ fixed |
| 6 | price ≤ 0 or outside no-arb bounds; v/s/k ≤ 0; NaN/inf; t > 100y; k > ~1e308 | Clean 400/422 | by design |
| 7 | IV solving to >200% | Solve + structured warning | by design |
| 8 | vega at solved IV < 0.01/1pt | Solve + `ill-conditioned` warning (fires on legitimately-quoted low-vega options too — see §4.4) | by design |
| 9 | k = 1e308, s = 1e-300, σ = 1e10, T = 99.9y | 200 with finite outputs | by design |
| 10 | Non-finite Greek (theoretical) | XML empty element / JSON null, no crash | by design |
| 11 | leg ids with XML-special or control characters | Sanitized; XML parses | by design |
| 12 | Friday/weekend expiry | Following roll extends T (§4.1) + discrepancy warning | documented |
| 13 | t granularity < 1 day | Whole-day rounding; 0-DTE floor adds up to the full day's time value (§4.1) | documented, test-pinned |
| 14 | `steps=500` explicitly | Interpreted as the "not overridden" sentinel → adaptive steps apply | documented trap |
| 15 | American cross-greeks, steps < 2000 | Volga is lattice noise; warning logged | warning added |
| 16 | Cross-greeks with v ≤ bump_vol_abs | 422 at schema level (stricter than the runtime 50% cap) | documented |
| 17 | `price=0` | IV = 0 (boundary solution) | by design |
| 18 | 500-leg American book, steps=5000 | ≈7 min single task vs 60s timeout → 503 | documented |
| ●19 | **Negative rates or negative carry: American IV upper bounds are wrong** | `upper = K` (put) / `S` (call) is only model-free when r ≥ 0 / carry ≥ 0. Measured: r=−1, q=5 ATM put truly prices at 156.96 (K=100); b=−0.5 deep-ITM call at 123.61 (S=100) — both **legitimately solvable prices rejected** as "above the no-arbitrage upper bound 100.000000" | **open** — fix: `upper = max(K, K·df_r)` / `max(S, S·df_qb)`; exotic corner (schema permits r ∈ [−1,5], b ∈ [−0.5,5]) but a wrong rejection is a wrong rejection |
| ●20 | CRR at very low vol (v ≲ 0.002 with drift) | Negative branch probability → clean 400 "Pricing failed for the given inputs" at *any* step count; JR prices the same case fine | workaround: `engine=binomial_jr`; message could name it |
| ●21 | JR engine theta/charm | Oscillate ±20% across N; Richardson is CRR-tuned (§2.3) | documented guidance |
| ●22 | Negative effective carry (b<0 or q<0) | delta can legitimately exceed ±1 (measured +1.182 at b=−0.5): delta bound is e^{−(q+b)T} | by design — do not alarm when \|delta\|>1 with negative carry |
| ●23 | r=−1, q=5 ATM put | Prices at 157 > K — correct (negative rates invert the classic put≤K bound) | by design (cf. #19) |
| ●24 | Intraday t (0–8h) | Priced at the 1-day floor: +0.27…+0.63 of extra value at ATM 30% (§4.1) | documented 0-DTE convention |

---

## 6. Recommendations (post round 2)

1. **Fix the American IV upper bounds for negative rates/carry** (#19) — two-line change (`max(K, K·df_r)` / `max(S, S·df_qb)`); exotic inputs, but currently rejects provably solvable prices.
2. Consider naming the JR fallback in the low-vol CRR failure message (#20) — one sentence.
3. Optionally tune `IV_LOW_VEGA_WARNING_THRESHOLD` 0.01 → 0.005 if the warning proves noisy on real quote streams (§4.4).
4. Withdrawn (round-2 verification): ITM-via-parity (§4.3 misdiagnosis); schema-visible `vega_at_iv` output remains available on approval.

*Round 1: 2026-10-12. Round 2: 2026-10-13. Probe scripts were transient and are not part of the repo. Re-measure when pricing-layer constants change.*
