"""Controlled vocabularies for child profile fields.

Hard rule 2: allergies and diet preference are enum/controlled-vocabulary fields,
never free text. These ``StrEnum`` classes are the single source of truth -- each is
mirrored by a native PostgreSQL enum type (design.md Decision 2), so an off-vocabulary
value is rejected by the database itself and not merely by application validation.

Member *values* become PostgreSQL enum labels. Renaming one is a migration, not a
refactor, so they are kept lowercase and stable.
"""

from enum import StrEnum


class Sex(StrEnum):
    """Biological sex, as required by growth-standard lookups.

    Restricted to the two values the WHO Child Growth Standards and CDC growth
    references are published for. Day 4's BMI-for-age and weight-for-age percentile
    lookups are sex-specific and have no defined curve for a third value, so admitting
    one here would create a profile for which no percentile can be computed.
    """

    MALE = "male"
    FEMALE = "female"


class DietPreference(StrEnum):
    """A household's dietary pattern for the child.

    Describes the dietary *pattern* only. Medically-driven exclusions belong in
    :class:`Allergen` or the doctor's note -- keeping the two apart means an allergy is
    never downgraded into a preference that a meal planner might treat as optional.
    """

    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    PESCATARIAN = "pescatarian"
    VEGAN = "vegan"

    @classmethod
    def default(cls) -> DietPreference:
        """The value used when a profile specifies no preference.

        The child-profile spec requires an unspecified preference to resolve to a real
        vocabulary member rather than null, so downstream meal planning never has to
        branch on a missing value.
        """
        return cls.OMNIVORE


class Allergen(StrEnum):
    """The major food allergens recognized by food-labelling regulation.

    The regulatory "big nine" (FASTER Act 2021, which added sesame to the prior eight).
    This list is closed on purpose: adding a member is a reviewed migration rather than
    a runtime insert, because a missing allergen in a meal plan is a safety failure.

    A child with no allergies carries an empty association set -- there is deliberately
    no ``NONE`` sentinel, which would otherwise be storable alongside real allergens.
    """

    MILK = "milk"
    EGG = "egg"
    PEANUT = "peanut"
    TREE_NUT = "tree_nut"
    SOY = "soy"
    WHEAT = "wheat"
    FISH = "fish"
    SHELLFISH = "shellfish"
    SESAME = "sesame"


class FeedingType(StrEnum):
    """What kind of feed a logged entry records (feeding-log spec, hard rule 2).

    Closed on purpose so a logged feed can always be turned into table nutrients: milk
    feeds map to the food table's ``milk_feed`` rows, solids name a table food, water
    contributes nothing. The PostgreSQL mirror of this enum ships with the Day 6
    ``feeding_log`` migration; until then entries are client-held and never stored.
    """

    BREASTMILK = "breastmilk"
    FORMULA = "formula"
    SOLID = "solid"
    WATER = "water"


class ActivityLevel(StrEnum):
    """Physical-activity categories of the 2005 DRI energy equations.

    A controlled vocabulary like the others here (hard rule 2); stored on the child
    profile as a PostgreSQL enum since Day 6.
    """

    SEDENTARY = "sedentary"
    LOW_ACTIVE = "low_active"
    ACTIVE = "active"
    VERY_ACTIVE = "very_active"
