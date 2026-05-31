---
name: Validation/compliance fix can drift a stress spec into REVIEW
description: When a backend validator is tightened, old stress specs sending invalid data start returning 422 — that's spec-drift, not a product regression.
---

When you add or tighten a backend validation/compliance rule (e.g. a Pydantic
`@field_validator` that rejects malformed input), any stress/E2E spec that was
previously sending **invalid placeholder data** to that endpoint will start
getting `422` and flip from PASS to REVIEW/FAIL.

**Why:** before the validator, garbage values were silently accepted; after, they
are correctly rejected. The product behavior is *more correct*, but the test data
is now wrong. This shows up as a counter-intuitive "the fix made metrics worse"
(REVIEW went up after a package landed).

**How to apply:** when a package adds a validator and a related spec newly REVIEWs,
check the *value the spec sends* before suspecting the product. Concrete example:
e-Fatura `customer_tax_number` validator requires 10/11-digit numeric (VKN/TCKN),
but the accounting-expenses stress spec sent `${prefix}ITX${i}00000` (alphabetic) →
422. Fix is in the **spec data** (send valid numeric), not loosening the validator.
Classify as SPEC-DRIFT, never weaken the assertion to make it green.
