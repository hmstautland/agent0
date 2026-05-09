# Approval logic
from config.settings import RULES

def request_permission(action, args, risk):
    rule = RULES.get(action, "ask")

    if risk == "low" or risk == "auto":    
        return True  # auto-allow

    print("\n--- PERMISSION REQUEST ---")
    print(f"Action: {action}")
    print(f"Risk: {risk}")
    print(f"Arguments: {args}")

    user_input = input("Approve? (y/n): ").lower()
    return user_input == "y";
