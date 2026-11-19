from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _cimalor_report_excluded_users(self):
        """People to leave out of the team views of the reports.

        The lists of the current companies (Settings › Users Left Out of the
        Reports). They only trim the views of Project administrators, who see
        everybody: a person who only sees themselves keeps seeing themselves,
        listed or not.
        """
        if not self.env.user.has_group("project.group_project_manager"):
            return self.browse()
        return self.env.companies.cimalor_excluded_user_ids

    @api.model
    def _cimalor_report_excluded_domain(self, field, operator, value):
        """Search domain of a report's "person left out" flag on `field`.

        For the action domains of Workload and Capacity, which cannot read the
        companies' lists themselves. `not in` keeps the rows without a person.
        """
        # One value, or a collection (a list in 18.0, an OrderedSet in 19.0).
        values = {value} if isinstance(value, bool) else set(value)
        wanted = {bool(item) for item in values}
        if operator in ("!=", "not in"):
            wanted = {True, False} - wanted
        excluded = self._cimalor_report_excluded_users()
        if wanted == {True, False}:
            return []
        if wanted == {True}:
            return [(field, "in", excluded.ids)]
        if wanted == {False}:
            return [(field, "not in", excluded.ids)]
        return [("id", "in", [])]
