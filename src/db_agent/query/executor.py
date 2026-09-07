from dataclasses import dataclass

from db_agent.adapters.base import DataSourceAdapter, QueryResult


@dataclass
class ExecutionOutcome:
    success: bool
    result: QueryResult | None = None
    error: str | None = None


def execute_query(adapter: DataSourceAdapter, query: str, row_limit: int, timeout_seconds: int) -> ExecutionOutcome:
    try:
        result = adapter.execute_query(query, row_limit=row_limit, timeout_seconds=timeout_seconds)
        return ExecutionOutcome(success=True, result=result)
    except TimeoutError as e:
        return ExecutionOutcome(success=False, error=f"Query timed out: {e}")
    except Exception as e:
        return ExecutionOutcome(success=False, error=str(e))