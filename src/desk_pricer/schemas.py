"""Pydantic request/response models."""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GreeksRequest(BaseModel):
    s: float = Field(gt=0, allow_inf_nan=False, description="Spot price of underlying")
    k: float = Field(gt=0, allow_inf_nan=False, description="Strike")
    t: float = Field(
        ge=0, le=100, allow_inf_nan=False,
        description="Time to expiry in years (ACT/365F); values < 1/365 are floored to 1 day"
    )
    r: float = Field(allow_inf_nan=False, description="Continuously compounded risk-free rate")
    q: float = Field(allow_inf_nan=False, description="Continuously compounded dividend yield")
    v: float = Field(gt=0, allow_inf_nan=False, description="Black volatility (decimal, not %)")
    type: Literal["call", "put"] = Field(description="Option type")
    style: Literal["european", "american"] = Field(description="Option style")
    engine: Literal["analytic", "binomial_crr", "binomial_jr", "fd"] | None = Field(
        default=None, description="Pricing engine"
    )
    steps: int = Field(default=400, ge=10, le=5000, description="Tree/FD steps")
    valuation_date: date | None = Field(default=None, description="Valuation date (ISO)")
    bump_spot_rel: float = Field(
        default=0.01, gt=0, le=0.1, allow_inf_nan=False,
        description="Relative spot bump for Greeks"
    )
    bump_vol_abs: float = Field(
        default=0.001, gt=0, le=0.01, allow_inf_nan=False,
        description="Absolute vol bump for Greeks"
    )
    bump_rate_abs: float = Field(
        default=0.001, gt=0, le=0.01, allow_inf_nan=False,
        description="Absolute rate bump for Greeks"
    )

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if isinstance(data, dict) and data.get("engine") == "":
            data["engine"] = None
        return data

    @model_validator(mode="after")
    def set_default_engine(self):
        if self.engine is None:
            if self.style == "european":
                self.engine = "analytic"
            else:
                self.engine = "binomial_crr"
        return self

    @model_validator(mode="after")
    def check_bump_size_vs_vol(self):
        if self.style == "american" and self.v <= self.bump_vol_abs:
            raise ValueError(
                "volatility must be greater than bump_vol_abs for American bump-and-revalue Greeks"
            )
        return self


class LegInput(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    qty: float = Field(allow_inf_nan=False, description="Quantity (negative for short)")
    s: float = Field(gt=0, allow_inf_nan=False)
    k: float = Field(gt=0, allow_inf_nan=False)
    t: float = Field(
        ge=0, le=100, allow_inf_nan=False,
        description="Time to expiry in years (ACT/365F); values < 1/365 are floored to 1 day"
    )
    r: float = Field(allow_inf_nan=False)
    q: float = Field(allow_inf_nan=False)
    v: float = Field(gt=0, allow_inf_nan=False)
    type: Literal["call", "put"]
    style: Literal["european", "american"]
    engine: Literal["analytic", "binomial_crr", "binomial_jr", "fd"] | None = Field(default=None)
    steps: int = Field(default=400, ge=10, le=5000)
    bump_spot_rel: float = Field(
        default=0.01, gt=0, le=0.1, allow_inf_nan=False,
        description="Relative spot bump for Greeks"
    )
    bump_vol_abs: float = Field(
        default=0.001, gt=0, le=0.01, allow_inf_nan=False,
        description="Absolute vol bump for Greeks"
    )
    bump_rate_abs: float = Field(
        default=0.001, gt=0, le=0.01, allow_inf_nan=False,
        description="Absolute rate bump for Greeks"
    )

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if isinstance(data, dict) and data.get("engine") == "":
            data["engine"] = None
        return data

    @model_validator(mode="after")
    def set_default_engine(self):
        if self.engine is None:
            if self.style == "european":
                self.engine = "analytic"
            else:
                self.engine = "binomial_crr"
        return self


class PortfolioRequest(BaseModel):
    valuation_date: date | None = Field(default=None)
    legs: list[LegInput] = Field(min_length=1, max_length=500)


class GreeksOutput(BaseModel):
    price: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    charm: float


class ImpliedVolRequest(BaseModel):
    s: float = Field(gt=0, allow_inf_nan=False, description="Spot price of underlying")
    k: float = Field(gt=0, allow_inf_nan=False, description="Strike")
    t: float = Field(
        ge=0, le=100, allow_inf_nan=False,
        description="Time to expiry in years (ACT/365F); values < 1/365 are floored to 1 day"
    )
    r: float = Field(allow_inf_nan=False, description="Continuously compounded risk-free rate")
    q: float = Field(allow_inf_nan=False, description="Continuously compounded dividend yield")
    price: float = Field(gt=0, allow_inf_nan=False, description="Observed market price of the option")
    type: Literal["call", "put"] = Field(description="Option type")
    style: Literal["european", "american"] = Field(description="Option style")
    engine: Literal["analytic", "binomial_crr", "binomial_jr", "fd"] | None = Field(
        default=None, description="Pricing engine"
    )
    steps: int = Field(default=400, ge=10, le=5000, description="Tree/FD steps")
    valuation_date: date | None = Field(default=None, description="Valuation date (ISO)")
    accuracy: float = Field(
        default=1e-4, gt=0, le=1e-2, allow_inf_nan=False,
        description="Brent solver accuracy"
    )
    max_iterations: int = Field(default=1000, ge=100, le=10000, description="Max solver iterations")

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if isinstance(data, dict) and data.get("engine") == "":
            data["engine"] = None
        return data

    @model_validator(mode="after")
    def set_default_engine(self):
        if self.engine is None:
            if self.style == "european":
                self.engine = "analytic"
            else:
                self.engine = "binomial_crr"
        return self


class ImpliedVolOutput(BaseModel):
    implied_vol: float
    npv_at_iv: float


class PnLAttributionGETRequest(BaseModel):
    s_t_minus_1: float = Field(gt=0, allow_inf_nan=False)
    s_t: float = Field(gt=0, allow_inf_nan=False)
    k: float = Field(gt=0, allow_inf_nan=False)
    t_t_minus_1: float = Field(
        ge=0, le=100, allow_inf_nan=False,
        description="Time to expiry in years (ACT/365F); values < 1/365 are floored to 1 day"
    )
    t_t: float = Field(
        ge=0, le=100, allow_inf_nan=False,
        description="Time to expiry in years (ACT/365F); values < 1/365 are floored to 1 day"
    )
    r_t_minus_1: float = Field(allow_inf_nan=False)
    r_t: float = Field(allow_inf_nan=False)
    q_t_minus_1: float = Field(allow_inf_nan=False)
    q_t: float = Field(allow_inf_nan=False)
    v_t_minus_1: float = Field(gt=0, allow_inf_nan=False)
    v_t: float = Field(gt=0, allow_inf_nan=False)
    type: Literal["call", "put"]
    style: Literal["european", "american"]
    engine: Literal["analytic", "binomial_crr", "binomial_jr", "fd"] | None = Field(default=None)
    steps: int = Field(default=400, ge=10, le=5000)
    qty: float = Field(default=1.0, allow_inf_nan=False)
    valuation_date_t_minus_1: date | None = Field(default=None)
    valuation_date_t: date | None = Field(default=None)
    method: Literal["backward", "average"] = Field(default="backward")
    bump_spot_rel: float = Field(
        default=0.01, gt=0, le=0.1, allow_inf_nan=False,
        description="Relative spot bump for Greeks"
    )
    bump_vol_abs: float = Field(
        default=0.001, gt=0, le=0.01, allow_inf_nan=False,
        description="Absolute vol bump for Greeks"
    )
    bump_rate_abs: float = Field(
        default=0.001, gt=0, le=0.01, allow_inf_nan=False,
        description="Absolute rate bump for Greeks"
    )

    @model_validator(mode="before")
    @classmethod
    def empty_str_to_none(cls, data):
        if isinstance(data, dict) and data.get("engine") == "":
            data["engine"] = None
        return data

    @model_validator(mode="after")
    def set_default_engine(self):
        if self.engine is None:
            self.engine = "analytic" if self.style == "european" else "binomial_crr"
        return self

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
    def check_bump_size_vs_vol(self):
        if self.style == "american" and self.v_t_minus_1 <= self.bump_vol_abs:
            raise ValueError(
                "volatility must be greater than bump_vol_abs for American bump-and-revalue Greeks"
            )
        return self
