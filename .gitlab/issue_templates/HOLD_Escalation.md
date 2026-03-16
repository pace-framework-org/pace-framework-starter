<!--
  PACE HOLD Escalation — GitLab Issue Template
  Use when a PACE plan has entered HOLD state and needs human intervention.
  PACE may open this automatically via GitLabTrackerAdapter.open_escalation_issue().
-->

## HOLD Details

| Field | Value |
| --- | --- |
| Plan ID / File | <!-- e.g. plans/feature-xyz/plan.yaml or story-3 --> |
| PACE Version | |
| Day Number | |
| GitLab Pipeline URL | |

## HOLD Reason Category

<!-- Check one -->
- [ ] Ambiguous requirement — needs clarification
- [ ] External dependency blocked (API, service, credential)
- [ ] Conflicting instructions in plan
- [ ] Test failure — human review required
- [ ] Budget / spend limit reached
- [ ] Security concern flagged by agent
- [ ] MR review required before proceeding
- [ ] Other: ___

## HOLD Message from PACE

```
Paste the exact HOLD message or log entry here
```

## Plan Context

**Goal:**

**Last completed step:**

**Blocking step:**

## Proposed Resolution

<!-- What action is needed to unblock? What decision is required? -->

## To Resume After Resolution

1. Resolve the blocker above
2. Close this issue
3. Set the `PACE_PAUSED` CI/CD variable to `false`
4. The PACE loop will re-run the blocked day on the next scheduled trigger

## Urgency / Deadline

<!-- e.g. Before EOD 2026-03-20, or Not urgent -->

/label ~hold ~escalation ~priority
