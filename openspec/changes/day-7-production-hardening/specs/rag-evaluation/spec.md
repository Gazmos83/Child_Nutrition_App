## MODIFIED Requirements

### Requirement: Both strategies are evaluated through the running service

The evaluation SHALL treat the service as a black box: it SHALL register an account for
itself before the first case, SHALL send knowledge-base cases to the question endpoint under
that account once per retrieval strategy (`basic`, `advanced`) with identical inputs, and
SHALL send routing, tool, user-data, and adversarial cases to the chat endpoint under the
same account after saving the case's child and feeding log to it. The evaluation SHALL NOT
import application code, SHALL NOT read the database directly, and SHALL NOT change prompts,
corpus, or retrieval parameters.

#### Scenario: A/B inputs are identical

- **WHEN** a knowledge-base case runs
- **THEN** the same question is posted twice, differing only in `strategy`, and both answers,
  citation sets, and retrieval statistics are recorded

#### Scenario: Chat cases use a throwaway account

- **WHEN** the chat cases run
- **THEN** the evaluation has registered a fresh account for this run, saved the case's
  child and feeding log to it, and reads nothing belonging to any other account

#### Scenario: Knowledge-base-only run still signs in

- **WHEN** the evaluation is run with only knowledge-base categories selected
- **THEN** it registers its account first and every question is posted with that session

#### Scenario: Service unchanged by a run

- **WHEN** an evaluation completes
- **THEN** no file under the knowledge base, nutrition data, or application source has
  changed
