# Excel Integration Guide

## Prerequisites

- Service running on `127.0.0.1:8765` (install via NSSM scripts)
- Excel with `WEBSERVICE` and `FILTERXML` functions (Excel 2013+)

## Single-Option Row Pattern

Assume columns:
- `C` = spot `s`
- `K` = strike `k`
- `T` = time to expiry `t`
- `R` = rate `r`
- `Q` = dividend yield `q`
- `V` = volatility `v`
- `TYPE` = `call` or `put`
- `STYLE` = `european` or `american`

### Build the URL

```excel
="http://127.0.0.1:8765/v1/greeks?s="&C2&"&k="&K2&"&t="&T2&"&r="&R2&"&q="&Q2&"&v="&V2&"&type="&TYPE2&"&style="&STYLE2
```

### Fetch Raw XML

```excel
=WEBSERVICE(H2)
```

### Extract Individual Greeks

| Cell | Formula |
|------|---------|
| Price | `=VALUE(FILTERXML(I2,"//outputs/price"))` |
| Delta | `=VALUE(FILTERXML(I2,"//outputs/delta"))` |
| Gamma | `=VALUE(FILTERXML(I2,"//outputs/gamma"))` |
| Vega  | `=VALUE(FILTERXML(I2,"//outputs/vega"))` |
| Theta | `=VALUE(FILTERXML(I2,"//outputs/theta"))` |
| Rho   | `=VALUE(FILTERXML(I2,"//outputs/rho"))` |
| Charm | `=VALUE(FILTERXML(I2,"//outputs/charm"))` |

## Status Cell

Show whether the service is up:

```excel
=IFERROR(FILTERXML(WEBSERVICE("http://127.0.0.1:8765/v1/health"),"//status")="UP","DOWN")
```

Or a simpler liveness check:

```excel
=IFERROR(FILTERXML(WEBSERVICE("http://127.0.0.1:8765/v1/health"),"//status"),"DOWN")
```

## Version Cell

```excel
=FILTERXML(WEBSERVICE("http://127.0.0.1:8765/v1/version"),"//service")
```

## Compact CSV (Excel 365)

If you have **Excel 365** with `TEXTSPLIT`, skip XML entirely. Add `&format=csv` to get a comma-separated list of `price,delta,gamma,vega,theta,rho,charm`:

```excel
=TEXTSPLIT(WEBSERVICE("http://127.0.0.1:8765/v1/greeks?s="&C2&"&k="&K2&"&t="&T2&"&r="&R2&"&q="&Q2&"&v="&V2&"&type="&TYPE2&"&style="&STYLE2&"&format=csv"),",")
```

This **spills** all 7 Greeks into adjacent cells automatically.

## Implied Volatility Cell

If you know the market price and want to back out IV:

```excel
="http://127.0.0.1:8765/v1/impliedvol?s="&C2&"&k="&K2&"&t="&T2&"&r="&R2&"&q="&Q2&"&price="&P2&"&type="&TYPE2&"&style="&STYLE2
```

Then extract the solved vol:

```excel
=VALUE(FILTERXML(J2,"//outputs/implied_vol"))
```

## Tips

1. **Throttle refreshes** — `WEBSERVICE` recalculates on every sheet change. For large sheets, consider VBA to batch-fetch into a cache table.
2. **Error handling** — wrap each `FILTERXML` in `IFERROR(...,"ERR")` so one bad row doesn't break the sheet.
3. **American options** — add `&steps=400` to the URL if you want explicit control; otherwise the service defaults to 400-step CRR.
4. **No Bloomberg in formulas** — the service is pure analytic; all market data comes from your existing `BDP`/`BDH` cells.
