import importlib
import json

from core.llm import query_llm
from core.speech_to_text import listen
from config.system_prompt import SYSTEM_PROMPT
from core.logger import log_event
from core.permission import request_permission
from tools.registry import TOOLS

# 🔁 Agent Flow
# 1. User input
# 2. LLM decides next action
# 3. Permission check
# 4. Tool executes
# 5. Result fed back to LLM
# 6. Repeat until complete

def execute_tool(action, args):
    tool_info = TOOLS[action]
    module_path, func_name = tool_info["func"].rsplit(".", 1)

    module = importlib.import_module(module_path)
    func = getattr(module, func_name)

    return func(**args);

def build_tool_prompt():
    lines = []

    for name, tool in TOOLS.items():
        lines.append(f"- {name}: {tool['description']}")

    return "\n".join(lines)

def run_agent(user_input, permission_decisions=None):
    log_event({"type": "user_input", "input": user_input})
    context = f"User request: {user_input}\n"
    print(f"Input: {user_input}")

    MAX_STEPS = 5
    for step in range(MAX_STEPS):
        decision_prompt  = SYSTEM_PROMPT + "\n" + context

        tool_prompt = build_tool_prompt()

        decision_prompt = f"""
        {SYSTEM_PROMPT}

        Available tools:
        {tool_prompt}

        {context}
        """
        
        raw = query_llm(decision_prompt)
        log_event({"type": "llm_raw_decision", "raw": raw})
        
        try:
            decision = json.loads(raw)
            print(f"LLM decision (raw): {raw}")
        except:
            return raw  # fallback if model fails JSON

        action = decision.get("action")
        print(f"Step {step} - LLM decision: {action}")

        # Final answer - no more action needed
        if action == "none":
            return decision.get("response")

        tool = TOOLS.get(action)

        if not tool:
            return f"Unknown action: {action}"
        
        args = decision.get("arguments", {})

        approved = request_permission(action, args, tool["risk"], decisions=permission_decisions, reason=decision.get("reason"))

        if not approved:
            return "Action denied"

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

      # Feed result back into context
        context += f"\nStep {step}:\nAction: {action}\nResult: {result}\n"

    return "Max steps reached without conclusion."


def run_agent_local(user_input, permission_action=None, permission_args=None, permission_risk=None):
    log_event({"type": "user_input", "input": user_input, "mode": "local_fallback"})
    context = f"User request: {user_input}\n"
    prompt = f"""
    You are a helpful assistant. Answer directly from your knowledge without using any tools or external access.
    
    User question: {user_input}
    """

    raw = query_llm(prompt)
    log_event({"type": "llm_raw_decision", "raw": raw, "mode": "local_fallback"})

    try:
        decision = json.loads(raw)
        action = decision.get("action")
        
        # If it's JSON with action == "none", return the response
        if action == "none":
            return decision.get("response")
        
        # If it's JSON without an action field but has a response, return that
        if "response" in decision and action is None:
            return decision.get("response")
        
        # If it has an action other than "none", it wants to use tools - trigger fallback
        if action and action != "none":
            return {
                "fallback_to_external": True,
                "message": "Local model could not answer directly; please try external tools.",
                "permission_action": permission_action,
                "permission_args": permission_args,
                "permission_risk": permission_risk
            }
    except Exception:
        # Not valid JSON - assume it's a plain text answer from the model
        pass
    
    # If we get here, either it's plain text or JSON without recognizable structure
    # Return it as the answer
    return raw

    # Send result back to LLM for summarization
    final_prompt = f"""
    User asked: {user_input}
    Tool result: {json.dumps(result, indent=2)}
    Summarize the key insights clearly and concisely.
    """

    return query_llm(final_prompt);

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
    
        