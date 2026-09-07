from db_agent.adapters.base import QueryResult


def process_result(result: QueryResult) -> dict:
    return {
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
    }