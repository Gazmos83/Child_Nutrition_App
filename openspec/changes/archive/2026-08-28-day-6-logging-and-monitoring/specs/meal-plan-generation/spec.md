## MODIFIED Requirements

### Requirement: Every meal-plan generation is logged with its full input snapshot

The system SHALL log, for every `generate_meal_plan` call, the full input snapshot (age,
weight, height, sex, diet preference, allergies, doctor's note text if present, and which
rule or source produced each target) sufficient to reconstruct why the plan was
generated the way it was (hard rule 8), and SHALL additionally record the gap report
(status, confidence, days, flags), the identifiers and timestamps of the day's logged
entries with their summed nutrients, and each adjustment the plan made because of them.
When the plan is generated inside a request, the record SHALL carry that request's
correlation identifier, the account identifier, and the stored child profile identifier
the inputs came from, so the recommendation can be traced to the account and profile that
received it.

#### Scenario: Log captures the full snapshot

- **WHEN** a meal plan is generated
- **THEN** a log record is emitted containing the child's age, weight, height, sex, diet
  preference, allergy set, doctor's note (if any), and the source of each nutrient
  target used

#### Scenario: Logging happens even when no plan can be produced

- **WHEN** the safety filter leaves no eligible foods
- **THEN** the input snapshot is still logged, alongside the no-safe-plan result

#### Scenario: Log names what informed an adjustment

- **WHEN** a plan is generated with a gap report and logged entries
- **THEN** the log record includes the gap report's status, confidence, days and flags,
  the logged entries' identifiers and summed nutrients, and the adjustments applied

#### Scenario: Log record is correlated to account and profile

- **WHEN** a plan is generated through the chat for a signed-in parent's saved child
- **THEN** the log record carries the request id, the account id, and the child profile id
