"""Keep historical tax snapshots separate from explicit synthetic definitions."""
POLICY = "demo-comp-tax-reconstruction-20261128-v1"
FIELDS = ("net_amount", "vat_amount", "tax_amount")


def concession_tax_basis(row):
    original = row.get("complimentary_original_tax_snapshot")
    if isinstance(original, dict) and all(original.get(key) is not None for key in FIELDS):
        return original
    synthetic = row.get("synthetic_comp_tax_definition")
    meta = row.get("demo_reconstruction") or {}
    if (isinstance(synthetic, dict) and synthetic.get("policy_id") == POLICY
        and synthetic.get("basis") == "explicit_new_synthetic_test_definition"
        and synthetic.get("historical_source_verified") is False
        and meta.get("policy_id") == POLICY and meta.get("historical_source_verified") is False):
        return synthetic
    return original
