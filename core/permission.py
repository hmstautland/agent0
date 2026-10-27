# Approval logic
from config.settings import RULES


def needs_approval(action, tool, granted=()):
    """Whether this tool call must be approved by the user before it runs.

    - RULES "ask" always asks.
    - External tools (tool["external"]) send data off the machine: they ask
      until the user has approved that tool once this session (`granted`).
    - RULES "auto" skips the prompt for any other tool.
    - Otherwise only low-risk tools run without asking.
    """
    rule = RULES.get(action)

    if rule == "ask":
        return True

    if tool.get("external"):
        return action not in granted

    if rule == "auto":
        return False

    return tool.get("risk") != "low"


def ask_cli(action, args, risk, reason=None):
    """CLI approval prompt. Returns True if the user approved."""
    print("\n--- PERMISSION REQUEST ---")
    print(f"Action: {action}")
    print(f"Risk: {risk}")
    if reason:
        print(f"Reason: {reason}")
    print(f"Arguments: {args}")

    user_input = input("Approve? (y/n): ").lower()
    return user_input == "y"
