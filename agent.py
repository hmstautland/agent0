import importlib
import json
import re

from core.llm import query_llm, OLLAMA_CODE_MODEL
from core.speech_to_text import listen
from config.system_prompt import SYSTEM_PROMPT
from core.logger import log_event
from core.permission import request_permission, PermissionRequired
from features.calendar.calendar import create_event, is_calendar_event_list, parse_create_command
from tools.registry import TOOLS
from features.audio.player import describe_play_result, parse_play_command, play_audio_file
from tools.files import parse_script_refactor_command

# 🔁 Agent Flow
# 1. User input
# 2. Try to answer directly from the local model (no tools)
# 3. If that's not enough, LLM decides next action using tools
# 4. Permission check
# 5. Tool executes
# 6. Result fed back to LLM
# 7. Repeat until complete

LOCAL_ONLY_PROMPT = """
You are a helpful assistant. Try to answer the user's question directly, from your own knowledge, without using any tools or external access.

Respond ONLY in JSON.

If you can answer directly:
{{
  "action": "none",
  "response": "your answer"
}}

If you cannot answer without a tool (web search, reading/writing files, email, calendar, etc.):
{{
  "action": "needs_tools"
}}

User question: {user_input}
"""

# Requests that talk about project files can never be answered from memory.
# Asked directly, the local model replies with manual "open the file and copy
# the block" instructions instead of reporting that it needs the tools, so
# these skip the local-first step entirely.
FILE_TASK_RE = re.compile(
    r"\.(py|html|css|js|json|md|txt|ics|fish|bat|toml|ya?ml)\b"
    r"|\b(file|files|project|codebase|repo|repository|template|templates|folder|directory)\b",
    re.I,
)


def needs_tools(user_input):
    return bool(user_input and FILE_TASK_RE.search(user_input))


def parse_decision(raw):
    """Parse the model's decision JSON. Returns a dict, or None if there is none.

    Small models wrap the object in markdown fences or an apology, so the JSON
    is dug out of the surrounding text rather than treated as a failure.
    """
    if not raw:
        return None

    text = str(raw).strip()

    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.lower().startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    try:
        decision = json.loads(text)
    except Exception:
        # Fall back to the outermost {...} span
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            decision = json.loads(text[start:end + 1])
        except Exception:
            return None

    return decision if isinstance(decision, dict) else None


def planned_first_decision(user_input):
    """Force the right first tool for intents the local model gets wrong.

    Returned as a normal decision, so it still goes through the permission
    gate and the result is still fed back into the loop.
    """
    script_args = parse_script_refactor_command(user_input)
    if script_args is not None:
        return {
            "action": "extract_inline_scripts",
            "arguments": script_args,
            "reason": "Move the inline script out to its own file and link it",
        }

    return None


def decision_args(decision):
    """The argument dict, under whichever key the model happened to use."""
    for key in ("arguments", "args", "parameters", "params", "input"):
        value = decision.get(key)
        if isinstance(value, dict):
            return value

    return {}


def execute_tool(action, args):
    tool_info = TOOLS[action]
    module_path, func_name = tool_info["func"].rsplit(".", 1)

    module = importlib.import_module(module_path)
    func = getattr(module, func_name)

    return func(**args)


def build_tool_prompt():
    lines = []

    for name, tool in TOOLS.items():
        lines.append(f"- {name}: {tool['description']}")

    return "\n".join(lines)


def try_local_answer(user_input):
    """Ask the local model to answer directly, without any tools.

    Returns the answer text, or None if the model needs a tool to proceed.
    """
    raw = query_llm(LOCAL_ONLY_PROMPT.format(user_input=user_input))
    log_event({"type": "llm_raw_decision", "raw": raw, "mode": "local_first"})

    decision = parse_decision(raw)
    if decision is None:
        # The local model was asked to respond in JSON and didn't - in
        # practice this means it got confused/refused (e.g. "I can't
        # interact with your calendar") rather than gave a real answer,
        # so treat it as needing a tool instead of trusting it as final.
        return None

    action = decision.get("action")
    if action in (None, "none"):
        return decision.get("response", raw)

    return None


def _run_steps(user_input, permission_decisions):
    """Core multi-step tool loop, shared by run_agent and stream_agent.

    Yields status/error/final_response/permission_required events. A
    permission_required event is only ever produced when permission_decisions
    is not None (the web flow) - with None (the CLI flow), request_permission
    blocks on input() instead of raising.
    """
    # Bypass the LLM for calendar-creation commands - the local model isn't
    # reliable at recognizing this needs the calendar tool rather than
    # answering "I can't do that" directly.
    calendar_command = parse_create_command(user_input)
    if calendar_command is not None:
        result = create_event(**calendar_command)
        yield {"event": "final_response", "response": f"{result}\n\nWould you like to see your calendar?"}
        return

    # Bypass the LLM for "play ..." requests - same reasoning as the calendar
    # bypass above. The result also carries structured "audio" data the web
    # UI needs (which file to load, or which candidates to offer); the CLI
    # just ignores that part and prints the text.
    play_args = parse_play_command(user_input)
    if play_args is not None:
        result = play_audio_file(**play_args)
        yield {"event": "final_response", "response": describe_play_result(result), "audio": result}
        return

    if needs_tools(user_input):
        yield {"event": "status", "message": "This needs the project tools, skipping the local model..."}
    else:
        yield {"event": "status", "message": "Trying local model..."}

        local_answer = try_local_answer(user_input)
        if local_answer is not None:
            yield {"event": "final_response", "response": local_answer}
            return

        yield {"event": "status", "message": "Local model needs tools, continuing..."}

    context = f"User request: {user_input}\n"
    attempted = set()
    json_retries_left = 2
    unknown_action_retries_left = 2
    pending_decision = planned_first_decision(user_input)

    MAX_STEPS = 8
    for step in range(MAX_STEPS):
        tool_prompt = build_tool_prompt()
        decision_prompt = f"""
        {SYSTEM_PROMPT}

        Available tools:
        {tool_prompt}

        {context}
        """

        if pending_decision is not None:
            decision, pending_decision = pending_decision, None
            raw = json.dumps(decision)
        else:
            decision = None
            yield {"event": "status", "message": f"Step {step + 1}: asking the LLM for next action..."}
            raw = query_llm(decision_prompt, model=OLLAMA_CODE_MODEL)

        log_event({"type": "llm_raw_decision", "raw": raw})
        yield {"event": "status", "message": "LLM decision complete."}

        if decision is None:
            decision = parse_decision(raw)

        if decision is None:
            # Mid-task prose is a broken contract, not an answer - nudge once,
            # then fall back to handing the text back as the reply.
            if json_retries_left > 0:
                json_retries_left -= 1
                context += (
                    "\nYour last reply was not valid JSON and was ignored. "
                    "Reply with ONLY a JSON object using the action format.\n"
                )
                yield {"event": "status", "message": "Model broke the JSON format, retrying..."}
                continue

            yield {"event": "final_response", "response": raw}  # fallback if model keeps failing JSON
            return

        action = decision.get("action")
        yield {"event": "status", "message": f"LLM chose action: {action}"}

        # Final answer - no more action needed
        if action == "none":
            yield {"event": "final_response", "response": decision.get("response")}
            return

        tool = TOOLS.get(action)
        if not tool:
            # Hallucinated tool - correct it instead of giving up
            if unknown_action_retries_left > 0:
                unknown_action_retries_left -= 1
                context += (
                    f"\nStep {step}:\nAction: {action}\n"
                    f"Result: There is no tool called '{action}'. "
                    f"Use one of: {', '.join(TOOLS)}.\n"
                )
                yield {"event": "status", "message": f"No such tool '{action}', retrying..."}
                continue

            yield {"event": "error", "message": f"Unknown action: {action}"}
            return

        args = decision_args(decision)

        # Small models get stuck repeating the same call - tell them instead of re-running it
        signature = f"{action}:{json.dumps(args, sort_keys=True, default=str)}"
        if signature in attempted:
            context += (
                f"\nStep {step}:\nAction: {action}\n"
                "Result: You already ran this exact action - its result is above. "
                "Do not repeat it. Choose a different action, or finish with action 'none'.\n"
            )
            continue
        attempted.add(signature)

        yield {"event": "status", "message": f"Requesting permission for tool: {action}"}

        try:
            approved = request_permission(action, args, tool["risk"], decisions=permission_decisions, reason=decision.get("reason"))
        except PermissionRequired as pr:
            yield {
                "event": "permission_required",
                "action": pr.action,
                "args": pr.tool_args,
                "risk": pr.risk,
                "reason": pr.reason,
                "input": user_input,
            }
            return
        except Exception as e:
            yield {"event": "error", "message": str(e)}
            return

        if not approved:
            yield {"event": "final_response", "response": "Action denied"}
            return

        yield {"event": "status", "message": f"Executing tool: {action}"}
        result = execute_tool(action, args)

        # Safely serialize result for logging (some tools return lists/dicts)
        try:
            result_preview = result if isinstance(result, str) else json.dumps(result, default=str)
        except Exception:
            result_preview = str(result)

        log_event({
            "type": "tool_execution",
            "step": step,
            "action": action,
            "args": args,
            "result": result_preview[:500]
        })

        yield {"event": "status", "message": f"Tool {action} completed."}

        # A calendar event list is shown as the month-grid calendar, not fed
        # back to the LLM for a text summary.
        if is_calendar_event_list(result):
            first = result[0]
            yield {
                "event": "final_response",
                "response": "",
                "show_calendar": {"year": first["date"].year, "month": first["date"].month},
            }
            return

        # Feed result back into context
        context += f"\nStep {step}:\nAction: {action}\nResult: {result}\n"

    yield {"event": "final_response", "response": "Max steps reached without conclusion."}


def run_agent(user_input, permission_decisions=None):
    """CLI/synchronous entry point. Drains _run_steps and returns the final text.

    permission_decisions=None makes request_permission fall back to an
    interactive input() prompt, so a permission_required event is not
    expected here - if one still arrives (e.g. called with a decisions dict,
    as the non-streaming web route does), it's re-raised for the caller.
    """
    log_event({"type": "user_input", "input": user_input})
    print(f"Input: {user_input}")

    final_response = "Max steps reached without conclusion."

    for event in _run_steps(user_input, permission_decisions):
        etype = event.get("event")

        if etype == "status":
            print(event["message"])
        elif etype in ("final_response", "error"):
            final_response = event.get("response", event.get("message"))
            if event.get("show_calendar"):
                # Hand the month to the caller (core/agent_routes.py's /ask)
                # so it can open the month-grid calendar.
                final_response = {"show_calendar": event["show_calendar"]}
        elif etype == "permission_required":
            raise PermissionRequired(event["action"], event["args"], event["risk"], reason=event.get("reason"))

    return final_response


def stream_agent(user_input, permission_decisions=None):
    """Web entry point. Yields status/final_response/error/permission_required events."""
    log_event({"type": "user_input", "input": user_input, "stream": True})

    # Empty (not None) decisions map for the web flow, so request_permission
    # raises PermissionRequired instead of blocking on input().
    if permission_decisions is None:
        permission_decisions = {}

    yield from _run_steps(user_input, permission_decisions)


if __name__ == "__main__":
    mode = input("Type (t) or Speak (s)? ").strip().lower()

    while True:

        if mode == "s":
            input("🎤 Press ENTER when ready to speak...")
            user_input = listen()
        else:
            user_input = input(">> ")

        if user_input.lower() in ["switch input mode"]:
            mode = input("Switch to Type (t) or Speak (s)? ").strip().lower()
            continue

        if user_input.lower() in ["switch to speech"]:
            mode = "s"
            continue

        if user_input.lower() in ["switch to text"]:
            mode = "t"
            continue

        if user_input.lower() in ["exit", "quit"]:
            print("Exiting agent.")
            break

        print(run_agent(user_input))
