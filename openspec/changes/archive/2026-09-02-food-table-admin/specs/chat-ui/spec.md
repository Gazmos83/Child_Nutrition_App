## ADDED Requirements

### Requirement: Administrators reach the food table from the app

When the signed-in account is an administrator the UI SHALL show a link to the food-table
page from the app's header. The page SHALL list every food with its state, offer a form to
create or edit a food in which the four safety questions are answered explicitly with nothing
preselected and the source is required, offer deactivate and reactivate, and offer a file
import with a dry-run preview that names each failing row before anything is written. A
signed-in non-administrator opening the page SHALL see a refusal and no data; a signed-out
visitor SHALL see the sign-in form. All copy on the page SHALL be direct.

#### Scenario: Administrator sees the link and the table

- **WHEN** an administrator opens the app
- **THEN** the header offers the food-table page and the page lists the foods

#### Scenario: Safety questions are not preselected

- **WHEN** an administrator opens the create form
- **THEN** none of the four safety questions has an answer, and saving is refused until all
  four are answered

#### Scenario: Dry run before import

- **WHEN** an administrator checks a file with one bad row
- **THEN** the panel lists that row's number, identifier, field, and message, says nothing
  was written, and the import button stays disabled

#### Scenario: Non-administrator is refused

- **WHEN** a signed-in account that is not an administrator opens the food-table page
- **THEN** the page states it is for administrators and shows no foods
