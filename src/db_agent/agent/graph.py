from langgraph.graph import StateGraph, START, END

from db_agent.agent.state import AgentState
from db_agent.agent.nodes.question_analysis import question_analysis
from db_agent.agent.nodes.schema_retrieval import schema_retrieval
from db_agent.agent.nodes.semantic_layer import semantic_layer
from db_agent.agent.nodes.query_generation import query_generation
from db_agent.agent.nodes.query_validation import query_validation, route_after_validation
from db_agent.agent.nodes.query_rewrite import query_rewrite
from db_agent.agent.nodes.query_execution import query_execution, route_after_execution
from db_agent.agent.nodes.result_analysis import result_analysis
from db_agent.agent.nodes.response_builder import response_builder


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("question_analysis", question_analysis)
    graph.add_node("schema_retrieval", schema_retrieval)
    graph.add_node("semantic_layer", semantic_layer)
    graph.add_node("query_generation", query_generation)
    graph.add_node("query_validation", query_validation)
    graph.add_node("query_rewrite", query_rewrite)
    graph.add_node("query_execution", query_execution)
    graph.add_node("result_analysis", result_analysis)
    graph.add_node("response_builder", response_builder)

    graph.add_edge(START, "question_analysis")
    graph.add_edge("question_analysis", "schema_retrieval")
    graph.add_edge("schema_retrieval", "semantic_layer")
    graph.add_edge("semantic_layer", "query_generation")
    graph.add_edge("query_generation", "query_validation")

    graph.add_conditional_edges(
        "query_validation",
        route_after_validation,
        {"execute": "query_execution", "retry": "query_rewrite", "give_up": "response_builder", "end": "response_builder"},
    )
    graph.add_edge("query_rewrite", "query_generation")

    graph.add_conditional_edges(
        "query_execution",
        route_after_execution,
        {"analyze": "result_analysis", "retry": "query_rewrite", "give_up": "response_builder", "end": "response_builder"},
    )
    graph.add_edge("result_analysis", "response_builder")
    graph.add_edge("response_builder", END)

    return graph.compile()


_compiled_graph = None


def get_agent():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph