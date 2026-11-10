"""The agent loop (Listing 13.4).

Ask the model for the next action, ask the gate whether it may run, log both,
and either carry the action out or tell the model why not. The run ends in a
permitted ending, an escalation, or an exhausted budget, which is also an
escalation.

The keyword arguments after max_steps exist for evaluate.py's comparison and
default to the production arrangement: gate is policy.check, the registry is
tools.TOOLS, and no person approves individual actions (L3). Passing
approver=Approver() gives the L2 arrangement, in which a person approves every
money action and resolves disagreements with Chapter 10.
"""
import policy
import tools
from escalation import escalate
from log import ActionLog

ENDINGS = {"close_refunded", "grant_final_credit", "file_chargeback"}
CLOSING_POWERS = {"deny_claim", "close_merchant_favour"}    # only reachable without the gate


class Approver:
    """A person approving money actions (L2). Minutes are illustrative."""
    APPROVE_MINUTES, CORRECT_MINUTES = 2.0, 8.0

    def approve(self, case, action, world):
        world.approvals += 1
        world.person_minutes += self.APPROVE_MINUTES
        return action

    def correct(self, case, action, world):
        """The person sees both choices and applies Chapter 10's decision."""
        world.approvals += 1
        world.person_minutes += self.CORRECT_MINUTES
        return tools.Action(case.recovery_decision, {}, "corrected by the approver")


def run_agent(case, model, world, max_steps=14, gate=None, registry=None, approver=None):
    gate = gate or policy.check
    registry = registry or tools.TOOLS
    state, log, done = world.state_for(case), ActionLog(case.case_id), {}
    observations = [tools.call("read_case", {}, case, f"{case.case_id}:read", done)]
    alerts = []
    for step in range(max_steps):
        action = model.next_action(case.brief(), observations, list(registry))
        verdict = gate(action, case, state, registry)
        log.write(step, action, verdict, config=policy.VERSION)
        if verdict.alert:
            alerts.append(action.name)
        if not verdict.allowed:
            if approver and verdict.reason == "decision_mismatch":
                action = approver.correct(case, action, world)
                verdict = policy.Verdict(True, "corrected_by_person")
                log.write(step, action, verdict, config=policy.VERSION)
            elif verdict.escalate:
                return escalate(case, log, verdict.reason, alerts)
            else:
                observations.append({"kind": "refusal", "action": action.name,
                                     "reason": verdict.reason})
                continue
        if action.name == "escalate":
            return escalate(case, log, action.args.get("reason", "agent"), alerts)
        if approver and registry[action.name].effect == "money" \
                and verdict.reason != "corrected_by_person":
            approver.approve(case, action, world)
        key = f"{case.case_id}:{action.name}:{action.args_hash()}"
        try:
            result = tools.call(action.name, action.args, case, key, done, registry)
        except TypeError as exc:                     # malformed call: fails before any system
            observations.append({"kind": "refusal", "action": action.name, "reason": str(exc)})
            continue
        state.update(action, result)
        observations.append(result)
        if action.name in ENDINGS or action.name in CLOSING_POWERS:
            return {"status": "done", "ending": action.name, "log": log, "alerts": alerts}
    return escalate(case, log, "budget", alerts)
