import inspect

from domains.hr import router as hr_router


def test_fnb_cost_and_supplier_reads_require_the_same_operation_as_mutations():
    """Cost, inventory value and supplier data must not be a login-only read."""
    for handler in (hr_router.get_recipes, hr_router.get_recipe, hr_router.list_ingredients):
        assert 'require_op("manage_sales")' in inspect.getsource(handler)
