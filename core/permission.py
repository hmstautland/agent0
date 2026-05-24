# Approval logic
from config.settings import RULES


class PermissionRequired(Exception):
    def __init__(self, action, args, risk, reason=None):
        self.action = action
        self.args = args
        self.risk = risk
        self.reason = reason
        super().__init__(f"Permission required for {action}")


def request_permission(action, args, risk, decisions=None, reason=None):
    rule = RULES.get(action, "ask")

    if risk == "low" or risk == "auto":
        return True  # auto-allow

    # If a decisions map is provided (web flow), use it or raise a PermissionRequired
    if decisions is not None:
        if action in decisions:
            return bool(decisions[action])
        # signal to caller that UI approval is required
        raise PermissionRequired(action, args, risk, reason=reason)

    # Fallback to CLI prompt
    print("\n--- PERMISSION REQUEST ---")
    print(f"Action: {action}")
    print(f"Risk: {risk}")
    print(f"Arguments: {args}")

    user_input = input("Approve? (y/n): ").lower()
    return user_input == "y"
