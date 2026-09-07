def infer_visualization(columns: list[str], rows: list[dict]) -> dict | None:
    """Very lightweight heuristic — chart-type suggestion based on result shape, not a hard requirement."""
    if not rows or len(columns) < 2:
        return None

    numeric_cols = [c for c in columns if isinstance(rows[0].get(c), (int, float))]
    categorical_cols = [c for c in columns if c not in numeric_cols]

    if len(categorical_cols) == 1 and len(numeric_cols) >= 1 and len(rows) <= 50:
        return {"type": "bar", "x": categorical_cols[0], "y": numeric_cols[0]}

    date_like_cols = [c for c in columns if "date" in c.lower() or "time" in c.lower() or "_at" in c.lower()]
    if date_like_cols and numeric_cols:
        return {"type": "line", "x": date_like_cols[0], "y": numeric_cols[0]}

    return None