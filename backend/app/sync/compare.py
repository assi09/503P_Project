"""How closely two daily tables agree, column by column: the check that a new data source
reproduces Fitbit's own numbers. Reports only aggregates, never individual values."""

import numpy as np
import pandas as pd


def agreement(candidate: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """Per shared column: days compared, share within 1% and 5%, median absolute difference."""
    rows = {}
    for column in candidate.columns.intersection(reference.columns):
        both = pd.concat([candidate[column], reference[column]], axis=1, keys=["a", "b"]).dropna()
        if both.empty:
            continue
        diff = (both["a"] - both["b"]).abs()
        # Relative to the reference; where it is zero only an exact match counts as close.
        nonzero = both["b"] != 0
        relative = pd.Series(
            np.where(nonzero, diff / both["b"].abs().where(nonzero), np.where(diff > 0, np.inf, 0)),
            index=both.index,
        )
        rows[column] = {
            "days": len(both),
            "within_1pct": (relative <= 0.01).mean(),
            "within_5pct": (relative <= 0.05).mean(),
            "median_abs_diff": diff.median(),
        }
    return pd.DataFrame.from_dict(rows, orient="index")
