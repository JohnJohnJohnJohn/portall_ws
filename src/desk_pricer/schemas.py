"""Pydantic request/response models."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GreeksRequest(BaseModel):
    s: float = Field(gt=0, description="Spot price of underlying")
    k: float = Field(gt=0, description="Strike")
    t: float = Field(gt=0, description="Time to expiry in years (ACT/365F)")
    r: float = Field(description="Continuously compounded risk-free rate")
    q: float = Field(description="Continuously compounded dividend yield")
    v: float = Field(gt=0, description="Black volatility (decimal, not %)")
    type: Literal["call", "put"] = Field(description="Option type")
    style: Literal["european", "american"] = Field(description="Option style")
    engine: Literal["analytic", "binomial_crr", "binomial_jr", "fd"] | None = Field(
        default=None, description="Pricing engine"
    )
    steps: int = Field(default=400, ge=10, le=5000, description="Tree/FD steps")
    valuation_date: date | None = Field(default=None, description="Valuation date (ISO)")
    bump_spot_rel: float = Field(default=0.01, gt=0, le=0.1, description="Relative spot bump for Greeks")
    bump_vol_abs: float = Field(default=0.0001, gt=0, le=0.01, description="Absolute vol bump for Greeks")
    bump_rate_abs: float = Field(default=0.0001, gt=0, le=0.01, description="Absolute rate bump for Greeks")

    @field_validator("engine", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

    @model_validator(mode="after")
    def set_default_engine(self):
        if self.engine is None:
            if self.style == "european":
                self.engine = "analytic"
            else:
                self.engine = "binomial_crr"
        return self


class LegInput(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    qty: float = Field(description="Quantity (negative for short)")
    s: float = Field(gt=0)
    k: float = Field(gt=0)
    t: float = Field(gt=0)
    r: float = Field()
    q: float = Field()
    v: float = Field(gt=0)
    type: Literal["call", "put"]
    style: Literal["european", "american"]
    engine: Literal["analytic", "binomial_crr", "binomial_jr", "fd"] | None = Field(default=None)
    steps: int = Field(default=400, ge=10, le=5000)

    @field_validator("engine", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

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
