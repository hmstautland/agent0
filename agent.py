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

def run_agent(user_input):
    log_event({"type": "user_input", "input": user_input})
    context = f"User request: {user_input}\n"
    print(f"Input: {user_input}")

    MAX_STEPS = 5
    for step in range(MAX_STEPS):
        decision_prompt  = SYSTEM_PROMPT + "\n" + context

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

        approved = request_permission(action, args, tool["risk"])

        if not approved:
            return "Action denied"

        result = execute_tool(action, args)

        log_event({
            "type": "tool_execution",
            "step": step,
            "action": action,
            "args": args,
            "result": result(result)[:500]
        })

      # Feed result back into context
        context += f"\nStep {step}:\nAction: {action}\nResult: {result}\n"

    return "Max steps reached without conclusion."

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
    
        