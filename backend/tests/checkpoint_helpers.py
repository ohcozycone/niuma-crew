"""Construct and inspect SDK state for migration and crash-recovery tests."""

from langgraph.graph import END, START, StateGraph

from app.execution.runtime.checkpoints import AgentRunState, checkpoint_config


def publication_graph(saver):
    graph = StateGraph(AgentRunState)
    graph.add_node("publish", lambda state: {})
    graph.add_edge(START, "publish")
    graph.add_edge("publish", END)
    return graph.compile(checkpointer=saver)


def checkpoint_values(store, run_id, checkpoint_id, *, thread_id=None):
    with store.reader() as saver:
        entry = saver.get_tuple(checkpoint_config(thread_id or run_id, checkpoint_id))
    if entry is None:
        raise RuntimeError("Missing checkpoint")
    return entry.checkpoint["channel_values"]
