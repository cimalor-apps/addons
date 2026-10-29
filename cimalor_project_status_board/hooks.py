MODULE = "cimalor_project_status_board"

# The stages this module creates (data/project_project_stage_data.xml).
MODULE_STAGES = ("project_project_stage_waiting", "project_project_stage_on_hold")

NATIVE_STAGE_TYPES = {
    "project.project_project_stage_0": "to_start",
    "project.project_project_stage_1": "in_progress",
    "project.project_project_stage_2": "done",
    # There is no "cancelled" state in the module: a cancelled project is
    # closed, so it counts as Done.
    "project.project_project_stage_3": "done",
}


def post_init_hook(env):
    """Turn on project stages and give the native stages their state type.

    Odoo only calls this hook on install, never on upgrade, so a -u does not
    undo what the administrator changed afterwards.
    """
    _enable_project_stages(env)
    _type_native_stages(env)


def _enable_project_stages(env):
    """Tick the "Project Stages" setting of the Project app.

    The board groups projects by `stage_id`, and that field is restricted to
    `project.group_project_stages`: without the setting there are no columns.

    It goes through the settings wizard on purpose, instead of adding the
    group to `base.group_user` in XML: it does exactly what ticking the box
    does (including showing the "Stage Changed" message subtype), and it
    stays an ordinary setting the administrator can untick. Uninstalling the
    module does not untick it.
    """
    env["res.config.settings"].create({"group_project_stages": True}).execute()


def _type_native_stages(env):
    """Map the four stages created by `project` to their state type.

    This is done here and not in an XML data file because the customer may
    have deleted those stages before installing: `env.ref` with
    `raise_if_not_found=False` skips the missing ones, where an XML record
    would try to recreate them and break the install.
    """
    for xmlid, state_type in NATIVE_STAGE_TYPES.items():
        stage = env.ref(xmlid, raise_if_not_found=False)
        if stage:
            stage.cimalor_state_type = state_type


def uninstall_hook(env):
    """Keep the Waiting and On Hold stages that still hold projects.

    On uninstall Odoo deletes every record the module's data created. A stage
    that still has projects cannot be deleted (`stage_id` is ondelete
    restrict): Odoo would log an error, delete the empty stage and keep the
    other one still tied to the module.

    Unlinking the XML id of the stages in use turns them into ordinary
    Project stages, so the projects keep their column and nothing fails.
    The empty ones keep their XML id and Odoo deletes them as usual.
    Archived projects count too: they also point at the stage.
    """
    Project = env["project.project"].with_context(active_test=False)
    for name in MODULE_STAGES:
        stage = env.ref(f"{MODULE}.{name}", raise_if_not_found=False)
        if stage and Project.search_count([("stage_id", "=", stage.id)], limit=1):
            env["ir.model.data"].search(
                [("module", "=", MODULE), ("name", "=", name)]
            ).unlink()
