"""Pydantic request/response models."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from deskpricer.pricing.conventions import (
    DAY_COUNT,
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_CALENDAR,
    DEFAULT_STEPS,
    MIN_T_YEARS,
)

EngineLiteral = Literal["analytic", "binomial_crr", "binomial_jr"]
CalendarLiteral = Literal["hong_kong", "us_nyse", "us_settlement", "united_kingdom", "null"]


class _EngineDefaultsMixin(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if isinstance(data, dict) and data.get("engine") == "":
            data = dict(data)
            data["engine"] = None
        return data

    @model_validator(mode="after")
    def set_default_engine(self):
        if self.engine is None:
            self.engine = "analytic" if self.style == "european" else "binomial_crr"
        return self


class _VanillaOptionCoreBase(_EngineDefaultsMixin, BaseModel):
    """Shared core fields for single-leg option pricing requests (no bumps)."""

    s: float = Field(gt=0, allow_inf_nan=False, description="Spot price of underlying")
    k: float = Field(gt=0, allow_inf_nan=False, description="Strike")
    t: float = Field(
        ge=0,
        le=100,
        allow_inf_nan=False,
        description=f"Time to expiry in years ({DAY_COUNT}); values < {MIN_T_YEARS} are floored to 1 day",
    )
    r: float = Field(allow_inf_nan=False, description="Continuously compounded risk-free rate")
    q: float = Field(allow_inf_nan=False, description="Continuously compounded dividend yield")
    type: Literal["call", "put"] = Field(description="Option type")
    style: Literal["european", "american"] = Field(description="Option style")
    engine: EngineLiteral | None = Field(default=None, description="Pricing engine")
    steps: int = Field(default=DEFAULT_STEPS, ge=10, le=5000, description="Tree/FD steps")
    calendar: CalendarLiteral = Field(
        default=DEFAULT_CALENDAR,
        description="QuantLib calendar identifier for holiday schedule and theta business-day counting",
    )


class _BumpParamsMixin(BaseModel):
    """Bump parameters shared by Greeks/Leg and PnL attribution requests."""

    bump_spot_rel: float = Field(
        default=DEFAULT_BUMP_SPOT_REL,
        ge=1e-9,
        le=0.1,
        allow_inf_nan=False,
        description="Relative spot bump for Greeks",
    )
    bump_vol_abs: float = Field(
        default=DEFAULT_BUMP_VOL_ABS,
        ge=1e-9,
        le=0.01,
        allow_inf_nan=False,
        description="Absolute vol bump for Greeks",
    )
    bump_rate_abs: float = Field(
        default=DEFAULT_BUMP_RATE_ABS,
        ge=1e-9,
        le=0.01,
        allow_inf_nan=False,
        description="Absolute rate bump for Greeks",
    )


class _VanillaOptionBase(_VanillaOptionCoreBase, _BumpParamsMixin):
    """Shared fields for single-leg option pricing requests with bump parameters."""

    v: float = Field(gt=0, allow_inf_nan=False, description="Black volatility (decimal, not %)")


class GreeksRequest(_VanillaOptionBase):
    valuation_date: date | None = Field(default=None, description="Valuation date (ISO)")


class LegInput(_VanillaOptionBase):
    id: str = Field(min_length=1, max_length=32)
    qty: float = Field(
        allow_inf_nan=False, ge=-1e12, le=1e12, description="Quantity (negative for short)"
    )


class PortfolioRequest(BaseModel):
    valuation_date: date | None = Field(default=None)
    legs: list[LegInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_unique_ids(self):
        ids = [leg.id for leg in self.legs]
        if len(ids) != len(set(ids)):
            raise ValueError("leg ids must be unique within a portfolio")
        return self


class GreeksOutput(BaseModel):
    price: float
    delta: float
    gamma: float
    vega: float
    theta: float = Field(
        description="P&L impact of one business day passing. Negative for typical "
        "long options (decay). Sign is opposite of Bloomberg DM<GO> "
        "convention where theta is reported as positive decay.",
    )
    rho: float
    charm: float


class ImpliedVolRequest(_VanillaOptionCoreBase):
    price: float = Field(
        ge=0, allow_inf_nan=False, description="Observed market price of the option"
    )
    valuation_date: date | None = Field(default=None, description="Valuation date (ISO)")
    accuracy: float = Field(
        default=1e-4, gt=0, le=1e-2, allow_inf_nan=False, description="Brent solver accuracy"
    )
    max_iterations: int = Field(default=1000, ge=100, le=10000, description="Max solver iterations")


class ImpliedVolOutput(BaseModel):
    implied_vol: float
    npv_at_iv: float


class PnLAttributionGETRequest(_EngineDefaultsMixin, _BumpParamsMixin, BaseModel):
    s_t_minus_1: float = Field(gt=0, allow_inf_nan=False)
    s_t: float = Field(gt=0, allow_inf_nan=False)
    k: float = Field(gt=0, allow_inf_nan=False)
    t_t_minus_1: float = Field(
        ge=0,
        le=100,
        allow_inf_nan=False,
        description=f"Time to expiry in years ({DAY_COUNT}); values < {MIN_T_YEARS} are floored to 1 day",
    )
    t_t: float = Field(
        ge=0,
        le=100,
        allow_inf_nan=False,
        description=f"Time to expiry in years ({DAY_COUNT}); values < {MIN_T_YEARS} are floored to 1 day",
    )
    r_t_minus_1: float = Field(allow_inf_nan=False)
    r_t: float = Field(allow_inf_nan=False)
    q_t_minus_1: float = Field(allow_inf_nan=False)
    q_t: float = Field(allow_inf_nan=False)
    v_t_minus_1: float = Field(gt=0, allow_inf_nan=False)
    v_t: float = Field(gt=0, allow_inf_nan=False)
    type: Literal["call", "put"]
    style: Literal["european", "american"]
    engine: EngineLiteral | None = Field(default=None)
    steps: int = Field(default=DEFAULT_STEPS, ge=10, le=5000)
    qty: float = Field(default=1.0, allow_inf_nan=False, ge=-1e12, le=1e12)
    valuation_date_t_minus_1: date | None = Field(default=None)
    valuation_date_t: date | None = Field(default=None)
    method: Literal["backward", "average"] = Field(default="backward")
    cross_greeks: bool = Field(default=False)
    calendar: CalendarLiteral = Field(
        default=DEFAULT_CALENDAR,
        description="QuantLib calendar identifier for holiday schedule and theta business-day counting",
    )

    @model_validator(mode="after")
    def check_date_order(self):
        if (
            self.valuation_date_t_minus_1 is not None
            and self.valuation_date_t is not None
            and self.valuation_date_t_minus_1 > self.valuation_date_t
        ):
            raise ValueError("valuation_date_t_minus_1 must not be after valuation_date_t")
        return self

    @model_validator(mode="after")
    def check_time_decay(self):
        if self.t_t > self.t_t_minus_1:
            raise ValueError("t_t must not be greater than t_t_minus_1")
        return self

    @model_validator(mode="after")
    def check_bump_size_vs_vol(self):
        if self.cross_greeks:
            for vol in (self.v_t_minus_1, self.v_t):
                if vol <= self.bump_vol_abs:
                    raise ValueError(
                        "volatility must be greater than bump_vol_abs for cross-greeks computation"
                    )
        return self
