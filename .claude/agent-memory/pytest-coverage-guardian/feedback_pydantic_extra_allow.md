---
name: pydantic-extra-allow-behavior
description: What Pydantic v2 extra=allow actually guarantees — and what it does not — relevant to test assertions
metadata:
  type: feedback
---

With Pydantic v2 `extra="allow"`:

- Extra fields are stored in `model_extra` (a dict).
- `getattr(instance, extra_field_name)` DOES return the value — this is intentional Pydantic v2 behavior, not a bug.
- The correct test assertions are:
  1. `extra_field_name in instance.model_extra` — it is captured
  2. `extra_field_name not in ModelClass.model_fields` — it is not a declared field
- Do NOT assert that `getattr` raises AttributeError for an extra field — it won't.

**Why:** Verified 2026-06-17 against Pydantic 2.13.4. Confused assertion would be a false positive.

**How to apply:** When writing or reviewing tests for models with `extra="allow"`, use `model_extra` and `model_fields` as the authoritative checks, not `getattr`.
