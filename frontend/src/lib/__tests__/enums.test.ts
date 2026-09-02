// Regenerate the fixture from the backend when a vocabulary changes:
//   uv run python -c "import json; from backend.models.enums import *; from backend.schemas.tools import ActivityLevel; from backend.rag.prompts import DISCLAIMER; print(json.dumps({'disclaimer': DISCLAIMER, 'sex':[m.value for m in Sex],'diet_preference':[m.value for m in DietPreference],'allergen':[m.value for m in Allergen],'activity_level':[m.value for m in ActivityLevel],'feeding_type':[m.value for m in FeedingType],'note_kind':[m.value for m in NoteKind]}, indent=2))" > frontend/src/lib/__tests__/fixtures/backend-enums.json
import { describe, expect, it } from "vitest";
import backend from "./fixtures/backend-enums.json";
import {
  ACTIVITY_LEVEL_OPTIONS,
  ALLERGEN_OPTIONS,
  DIET_PREFERENCE_OPTIONS,
  FEEDING_TYPE_OPTIONS,
  NOTE_KIND_OPTIONS,
  SEX_OPTIONS,
} from "../enums";

describe("controlled vocabularies match the backend", () => {
  it("sex", () => {
    expect(SEX_OPTIONS.map((o) => o.value)).toEqual(backend.sex);
  });
  it("diet preference", () => {
    expect(DIET_PREFERENCE_OPTIONS.map((o) => o.value)).toEqual(backend.diet_preference);
  });
  it("allergens are the regulatory big nine", () => {
    expect(ALLERGEN_OPTIONS.map((o) => o.value)).toEqual(backend.allergen);
    expect(ALLERGEN_OPTIONS).toHaveLength(9);
  });
  it("activity level", () => {
    expect(ACTIVITY_LEVEL_OPTIONS.map((o) => o.value)).toEqual(backend.activity_level);
  });
  it("feeding type", () => {
    expect(FEEDING_TYPE_OPTIONS.map((o) => o.value)).toEqual(backend.feeding_type);
  });
  it("note kind", () => {
    expect(NOTE_KIND_OPTIONS.map((o) => o.value)).toEqual(backend.note_kind);
  });
  it("every option has a human label", () => {
    for (const option of [
      ...SEX_OPTIONS,
      ...DIET_PREFERENCE_OPTIONS,
      ...ALLERGEN_OPTIONS,
      ...ACTIVITY_LEVEL_OPTIONS,
      ...FEEDING_TYPE_OPTIONS,
      ...NOTE_KIND_OPTIONS,
    ]) {
      expect(option.label.trim().length).toBeGreaterThan(0);
      expect(option.label).not.toContain("_");
    }
  });
});
