from __future__ import annotations

import math
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
Op = Literal["add", "sub", "mul", "div"]


class CalcRequest(BaseModel):
    op: Op
    a: FiniteFloat = Field(description="Left operand")
    b: FiniteFloat = Field(description="Right operand")


class CalcResponse(BaseModel):
    op: Op
    a: FiniteFloat
    b: FiniteFloat
    result: FiniteFloat


app = FastAPI(title="Dummy Calculator API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _calc(op: Op, a: float, b: float) -> float:
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return a * b
    if op == "div":
        if b == 0:
            raise HTTPException(status_code=400, detail="Division by zero.")
        return a / b
    raise HTTPException(status_code=400, detail=f"Unsupported op: {op}")


@app.post("/calc", response_model=CalcResponse)
def calc(payload: CalcRequest) -> CalcResponse:
    result = _calc(payload.op, payload.a, payload.b)
    if not math.isfinite(result):
        raise HTTPException(status_code=400, detail="Non-finite result.")
    return CalcResponse(op=payload.op, a=payload.a, b=payload.b, result=result)


@app.get("/calc/{op}", response_model=CalcResponse)
def calc_get(op: Op, a: FiniteFloat, b: FiniteFloat) -> CalcResponse:
    result = _calc(op, a, b)
    if not math.isfinite(result):
        raise HTTPException(status_code=400, detail="Non-finite result.")
    return CalcResponse(op=op, a=a, b=b, result=result)

