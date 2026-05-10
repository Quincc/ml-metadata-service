from __future__ import annotations

import io
from typing import Any

import pandas as pd


_DTYPE_TO_TYPE = {
    "int": "int",
    "float": "float",
    "bool": "bool",
    "datetime": "datetime",
    "object": "string",
    "string": "string",
    "category": "string",
}


def _normalize_dtype(dtype) -> str:
    name = str(dtype).lower()
    for prefix, mapped in _DTYPE_TO_TYPE.items():
        if name.startswith(prefix):
            return mapped
    return "string"


def infer_schema_from_csv(file_bytes: bytes, sample_rows: int = 5000) -> dict[str, Any]:
    """Infer a schema_json definition from a CSV byte payload."""
    if not file_bytes:
        raise ValueError("CSV file is empty")
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), nrows=sample_rows)
    except Exception as exc:  # pandas raises various subclasses
        raise ValueError(f"Failed to parse CSV: {exc}") from exc

    if df.empty and not df.columns.size:
        raise ValueError("CSV has no columns")

    fields = [
        {"name": str(col), "type": _normalize_dtype(df[col].dtype), "nullable": bool(df[col].isna().any())}
        for col in df.columns
    ]
    return {"fields": fields, "row_count_sampled": int(len(df))}
