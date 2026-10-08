# Approval logic
from config.settings import RULES


class PermissionRequired(Exception):
    def __init__(self, action, args, risk, reason=None):
        super().__init__(f"Permission required for {action}")
        self.action = action
        self.tool_args = args
        self.risk = risk
        self.reason = reason


def request_permission(action, args, risk, decisions=None, reason=None):
    rule = RULES.get(action)

    if rule == "auto":
        return True  # auto-allow, per configured rule

    # No explicit rule for this action - fall back to risk level
    if rule is None and (risk == "low" or risk == "auto"):
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
