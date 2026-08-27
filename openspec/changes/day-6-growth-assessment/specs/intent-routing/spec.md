## ADDED Requirements

### Requirement: Growth questions about the parent's child route to the growth tool

A message asking where the parent's own child sits on a growth chart — their percentile,
their BMI, or whether their weight or length is normal for their age — SHALL route to the
growth-assessment tool (alone, or alongside the guideline search when the parent also
asks what the result means). Child arguments SHALL be filled from the request's child
context as for every other tool; a missing length/height SHALL NOT be treated as a
failure, because the tool computes what it can.

#### Scenario: BMI question with child context

- **WHEN** the parent asks "what's her BMI?" with child context supplied
- **THEN** the routing decision includes the growth-assessment tool

#### Scenario: Growth question without a height

- **WHEN** the parent asks whether their child's weight is normal for their age and the
  child context has no height
- **THEN** the growth-assessment tool runs successfully with weight-for-age only and the
  tool entry reports success, not failure

#### Scenario: Growth question without child context

- **WHEN** the parent asks for their child's percentile and no child context is supplied
- **THEN** the response carries the existing missing-details hint pointing to the side
  panel
