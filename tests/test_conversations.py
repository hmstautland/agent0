import core.conversations as conversations
import tools.registry as registry
from storage.conversations import recent_turns, save_turn


def test_history_is_the_newest_turns_as_chat_messages_oldest_first(conversation_db):
    cid = conversations.new_conversation()
    for n in range(8):
        save_turn(cid, f"question {n}", f"answer {n}")

    messages = conversations.history_messages(cid)

    assert len(messages) == 2 * conversations.HISTORY_TURNS
    assert messages[0] == {"role": "user", "content": "question 2"}
    assert messages[-1] == {"role": "assistant", "content": "answer 7"}


def test_history_lists_what_the_tools_did_and_shortens_long_answers(conversation_db):
    cid = conversations.new_conversation()
    save_turn(cid, "add light mode", "x" * 5000, ["read_files static/styles.css", "edit_file static/styles.css"])

    reply = conversations.history_messages(cid)[1]["content"]

    assert reply.startswith("[Tools used: read_files static/styles.css; edit_file static/styles.css]\n")
    assert reply.endswith(" [...]")
    assert len(reply) < conversations.TURN_ANSWER_CHARS + 100


def test_history_drops_the_oldest_turns_to_stay_in_budget(conversation_db):
    cid = conversations.new_conversation()
    save_turn(cid, "old", "a" * 1000)
    save_turn(cid, "new", "b" * 1000)

    messages = conversations.history_messages(cid, budget=1500)

    assert [m["content"] for m in messages if m["role"] == "user"] == ["new"]


def test_conversations_do_not_see_each_other(conversation_db):
    first, second = conversations.new_conversation(), conversations.new_conversation()
    save_turn(first, "mine", "yes")

    assert conversations.history_messages(second) == []
    assert conversations.history_messages(None) == []


def test_search_history_shapes_the_matches_for_the_model(conversation_db):
    save_turn(conversations.new_conversation(), "make the UI support light mode", "Done. " * 200, ["edit_file static/styles.css"])

    [found] = conversations.search_history("styles.css")

    assert found["question"] == found["conversation"] == "make the UI support light mode"
    assert found["tools_used"] == ["edit_file static/styles.css"]
    assert len(found["answer"]) <= conversations.SEARCH_ANSWER_CHARS + len(" [...]")
    assert conversations.search_history("nothing like this") == "No earlier conversations matched."


def test_search_history_says_when_there_is_nothing_yet(conversation_db):
    assert conversations.search_history() == "No earlier conversations yet."


def test_record_stores_the_final_answer_or_error_and_passes_events_through(conversation_db):
    cid = conversations.new_conversation()
    actions = []
    events = [{"event": "status", "message": "..."}, {"event": "final_response", "response": "", "show_calendar": {"year": 2026, "month": 3}}]

    passed = []
    for event in conversations.record(events, cid, "show my calendar", actions):
        passed.append(event)
        actions.append("read_calendar")  # filled in while the run goes on

    assert passed == events
    turn = recent_turns(cid, 10)[0]
    assert (turn["answer"], turn["actions"]) == ("(Opened the calendar at 2026-03)", "read_calendar")

    list(conversations.record([{"event": "error", "message": "Ollama is down"}], cid, "hi"))
    assert recent_turns(cid, 10)[-1]["answer"] == "(Failed: Ollama is down)"


def test_search_history_is_a_low_risk_registry_tool():
    tool = registry.TOOLS["search_history"]
    assert tool["func"] == "core.conversations.search_history"
    assert tool["risk"] == "low" and not tool.get("external")
