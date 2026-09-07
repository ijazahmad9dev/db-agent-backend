import concurrent.futures
import duckdb


def run_with_timeout(con: duckdb.DuckDBPyConnection, query: str, timeout_seconds: int):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(con.execute, query)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            con.interrupt()
            raise TimeoutError(f"Query exceeded {timeout_seconds}s timeout")