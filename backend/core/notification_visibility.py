"""Shared audience clauses for the notification bell and legacy endpoints."""


def role_value(user):
    role = getattr(user, "role", None)
    return getattr(role, "value", str(role))


def visibility_filter(user):
    # Both constraints apply: specifying a role must never widen a private
    # recipient list. Missing/empty audiences retain legacy broadcast behavior.
    return {
        "$and": [{"$or": [
            {"target_user_ids": {"$exists": False}}, {"target_user_ids": None},
            {"target_user_ids": {"$size": 0}}, {"target_user_ids": user.id},
        ]}],
        "$or": [
            {"target_roles": {"$exists": False}}, {"target_roles": None},
            {"target_roles": {"$size": 0}}, {"target_roles": role_value(user)},
        ],
    }
