## ADDED Requirements

### Requirement: The overridable nutrient set is independent of the displayed set

The set of nutrients a doctor's note may override SHALL remain exactly calories, protein,
and iron, and SHALL NOT widen when the set of nutrients the system displays or tracks
widens. An extraction naming a nutrient that the system displays but does not accept for
override SHALL be rejected in the same way as any other unrecognized nutrient, and SHALL
degrade to "note not applied, flagged" rather than being silently dropped.

This boundary is stated explicitly because a wider displayed set invites the misreading
that anything displayed can be overridden. Widening it would mean asking the language model
to extract more units from free clinical text and would introduce interactions with
tolerable upper intake levels, for no user-visible gain.

#### Scenario: A note naming a displayed but non-overridable nutrient is rejected

- **WHEN** a doctor's note states a daily calcium limit, and calcium is among the nutrients
  displayed for the child
- **THEN** the extraction is rejected rather than applied
- **AND** the response flags that the note could not be applied, naming the reason
- **AND** the calcium target remains the general reference value

#### Scenario: The overridable set does not follow the displayed set

- **WHEN** the displayed target set is widened to include additional nutrients
- **THEN** the nutrients accepted for override are still exactly calories, protein, and iron

#### Scenario: An overridable nutrient still applies normally

- **WHEN** a doctor's note limits calories and the child's displayed set contains six
  nutrients
- **THEN** the calorie override is applied and the conflict is reported as before
- **AND** no other displayed nutrient's target is altered by the note
