"""The two exclusion filters of the settings, shared by projects and tasks.

Settings › Excluded Projects and Excluded Tasks are domains kept as text in
ir.config_parameter. Each model keeps a stored `cimalor_excluded` flag in step
with its filter, because the Workload report is a database view and needs a
column to filter on.
"""

from ast import literal_eval

from odoo.exceptions import UserError

PROJECT_PARAM = "cimalor_project_status_board.excluded_project_domain"
TASK_PARAM = "cimalor_project_status_board.excluded_task_domain"

# Set while the flags are being written, so write() does not refresh again.
REFRESHING = "cimalor_refreshing_excluded"


def excluded_domain(env, param):
    """The filter as a domain list, or False when it is empty.

    An empty filter excludes nothing: an empty domain would match every
    record, which is never what an empty setting means.
    """
    value = env["ir.config_parameter"].sudo().get_str(param).strip()
    domain = literal_eval(value) if value else []
    return domain or False


def check_domain(model, value, label):
    """Refuse a filter that cannot be used, before it is saved."""
    try:
        domain = literal_eval(value.strip()) if value and value.strip() else []
        model.with_context(active_test=False).search(domain, limit=1)
    except (SyntaxError, TypeError, ValueError) as error:
        raise UserError(
            model.env._(
                "The %(filter)s filter cannot be used: %(error)s",
                filter=label,
                error=error,
            )
        ) from error


def refresh_flags(model, param, records=None):
    """Write `cimalor_excluded` on `records` (all records when None).

    As superuser: the settings are company-wide and apply to every record,
    whether the current user sees it or not; only this flag is written.
    Returns the records whose flag changed.
    """
    Model = model.sudo().with_context(active_test=False, **{REFRESHING: True})
    scope = Model.browse(records.ids) if records is not None else None
    domain = excluded_domain(model.env, param)
    if domain:
        if scope is not None:
            domain = [("id", "in", scope.ids)] + domain
        excluded = Model.search(domain)
    else:
        excluded = Model.browse()
    if scope is None:
        scope = Model.search([("cimalor_excluded", "=", True)]) | excluded
    flagged = scope.filtered("cimalor_excluded")
    newly, released = excluded - flagged, flagged - excluded
    newly.write({"cimalor_excluded": True})
    released.write({"cimalor_excluded": False})
    return newly | released
