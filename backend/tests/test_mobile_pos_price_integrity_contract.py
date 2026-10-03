import inspect

from domains.pms.mobile_router import pos


def test_mobile_menu_price_update_keeps_canonical_price_fields_in_sync():
    source = inspect.getsource(pos.update_menu_item_price_mobile)

    assert '"price": new_price' in source
    assert '"unit_price": new_price' in source
    assert "math.isfinite(new_price)" in source


def test_quick_order_quantity_has_positive_bounded_validation():
    field = pos.QuickOrderItem.model_fields["quantity"]

    assert field.default == 1
    assert "Ge(ge=1)" in repr(field.metadata)
    assert "Le(le=999)" in repr(field.metadata)
