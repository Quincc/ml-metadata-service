from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preprocess the Titanic dataset and export cleaned data plus schema JSON.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the raw Titanic CSV file, for example data/raw/Titanic-Dataset.csv",
    )
    parser.add_argument(
        "--output",
        default="data/processed/train_cleaned.csv",
        help="Path to the cleaned CSV file",
    )
    parser.add_argument(
        "--schema-output",
        default="data/schemas/train_cleaned_schema.json",
        help="Path to the generated schema JSON file",
    )
    return parser


def normalize_dtype(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    return "string"


def create_schema(df: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    return {
        "fields": [
            {"name": column, "type": normalize_dtype(df[column])}
            for column in df.columns
        ]
    }


def preprocess_titanic(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()

    if "Age" in cleaned.columns:
        cleaned["Age"] = cleaned["Age"].fillna(cleaned["Age"].median())
    if "Fare" in cleaned.columns:
        cleaned["Fare"] = cleaned["Fare"].fillna(cleaned["Fare"].median())
    if "Embarked" in cleaned.columns and cleaned["Embarked"].dropna().any():
        cleaned["Embarked"] = cleaned["Embarked"].fillna(cleaned["Embarked"].mode().iloc[0])

    if {"SibSp", "Parch"}.issubset(cleaned.columns):
        cleaned["FamilySize"] = cleaned["SibSp"] + cleaned["Parch"] + 1

    if "Sex" in cleaned.columns:
        cleaned["SexEncoded"] = cleaned["Sex"].map({"male": 0, "female": 1}).fillna(-1).astype(int)

    if "Embarked" in cleaned.columns:
        embarked_mapping = {"S": 0, "C": 1, "Q": 2}
        cleaned["EmbarkedEncoded"] = (
            cleaned["Embarked"].map(embarked_mapping).fillna(-1).astype(int)
        )

    columns_to_drop = [
        column
        for column in ["Cabin", "Name", "Ticket", "Sex", "Embarked"]
        if column in cleaned.columns
    ]
    cleaned = cleaned.drop(columns=columns_to_drop)

    preferred_order = [
        "PassengerId",
        "Survived",
        "Pclass",
        "SexEncoded",
        "Age",
        "SibSp",
        "Parch",
        "Fare",
        "EmbarkedEncoded",
        "FamilySize",
    ]
    ordered_columns = [column for column in preferred_order if column in cleaned.columns]
    tail_columns = [column for column in cleaned.columns if column not in ordered_columns]
    cleaned = cleaned[ordered_columns + tail_columns]

    return cleaned


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    schema_output_path = Path(args.schema_output)

    df = pd.read_csv(input_path)
    cleaned = preprocess_titanic(df)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema_output_path.parent.mkdir(parents=True, exist_ok=True)

    cleaned.to_csv(output_path, index=False)
    schema_output_path.write_text(
        json.dumps(create_schema(cleaned), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Saved cleaned dataset to: {output_path}")
    print(f"Saved schema JSON to: {schema_output_path}")
    print(f"Rows: {len(cleaned)}")
    print(f"Columns: {list(cleaned.columns)}")


if __name__ == "__main__":
    main()
