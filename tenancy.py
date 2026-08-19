"""Automatic per-account (tenant) data isolation.

This app connects to Postgres directly as the table owner, which BYPASSES
Supabase Row Level Security. Therefore the load-bearing isolation is enforced
here, at the application layer:

  * Every SELECT against a tenant model (any model with an ``account_id``
    column, except ``accounts``/``users``) is transparently filtered to the
    current request's account via ``with_loader_criteria``.
  * Every INSERT of a tenant model is stamped with the current account id.

The current account is read from ``flask.g.account_id`` which is set once per
request from the authenticated user (see ``routes.py`` ``before_request``).

Fail-safe: when a request is authenticated but has no account id, the account
is treated as ``-1`` (matches nothing) so a mis-provisioned user can never see
another tenant's data. Outside a request context (startup migrations, backfill)
no filter is applied, so bootstrap code retains full access.
"""
import logging
from flask import g, has_request_context
from flask_login import current_user
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

# Populated by register(); model classes that are account-scoped.
_tenant_models = []

# Tables that carry account_id but are NOT auto-filtered (the auth layer scopes
# these explicitly so login / user_loader / team management keep working).
_EXCLUDE_TABLES = {'accounts', 'users'}


# Guard flag on ``g`` marking that we are part-way through resolving the
# current user. See current_account_id() for why it is needed.
_RESOLVING = '_tenant_account_resolving'


def current_account_id():
    """The account id the current request is allowed to touch, or None when
    there is no request (startup/CLI) so bootstrap code keeps full access.

    Must stay cheap: the ORM hook below calls this on *every* SELECT.
    """
    if not has_request_context():
        return None
    acc = g.get('account_id', 'unset')
    if acc != 'unset':
        return acc

    # Reaching current_user here runs Flask-Login's user_loader, which issues
    # a SELECT — and that SELECT re-enters this function through the ORM hook,
    # which reads current_user again. Each query therefore spawned another user
    # lookup: measured at 57-61 redundant SELECTs per screen, roughly 90% of
    # all database traffic. Harmless on local SQLite (~2ms); on Supabase every
    # one is a network round trip.
    #
    # The guard breaks that loop. While resolving we answer -1, which matches
    # no tenant row, so the fallback fails closed rather than unfiltered.
    if g.get(_RESOLVING):
        return -1
    setattr(g, _RESOLVING, True)
    try:
        if current_user.is_authenticated:
            return current_user.account_id or -1
    except Exception:
        pass
    finally:
        setattr(g, _RESOLVING, False)
    return None


def set_request_account():
    """Call from a before_request hook: pin the account for this request.

    Pinning a provisional value *before* touching current_user is the point:
    reading it triggers the user_loader query, which trips the tenant filter
    while g.account_id does not yet exist. -1 is the fail-closed choice — the
    only query in that window is the user lookup itself, and ``users`` is
    never tenant-filtered.
    """
    g.account_id = -1
    try:
        if current_user.is_authenticated:
            g.account_id = current_user.account_id or -1
        else:
            g.account_id = None
    except Exception:
        g.account_id = None


def register(db):
    """Discover tenant models and wire the SELECT filter + INSERT stamping."""
    global _tenant_models
    _tenant_models = []
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        table = getattr(cls, '__tablename__', None)
        if table in _EXCLUDE_TABLES:
            continue
        if hasattr(cls, 'account_id'):
            _tenant_models.append(cls)

    # Stamp account_id on insert for every tenant model.
    def _stamp(mapper, connection, target):
        if getattr(target, 'account_id', None) is None:
            acc = current_account_id()
            if acc is not None and acc != -1:
                target.account_id = acc

    for cls in _tenant_models:
        event.listen(cls, 'before_insert', _stamp)

    logging.info("Tenant isolation active on %d models: %s",
                 len(_tenant_models),
                 ', '.join(sorted(c.__tablename__ for c in _tenant_models)))


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(execute_state):
    # Only filter primary entity SELECTs. Relationship/column (lazy) loads are
    # already constrained by their foreign key to an in-account parent, and
    # re-filtering them can break eager loads — the documented safe scope.
    if not execute_state.is_select:
        return
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    account_id = current_account_id()
    if account_id is None:
        return  # no request context (startup/backfill) → unfiltered
    options = [
        with_loader_criteria(cls, cls.account_id == account_id, include_aliases=True)
        for cls in _tenant_models
    ]
    if options:
        execute_state.statement = execute_state.statement.options(*options)
