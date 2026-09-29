from odoo import Command

WELCOME_TEMPLATE = "cimalor_team_todo.team_todo_onboarding"


def post_init_hook(env):
    """Seed the administrators and hand each of them a welcome task.

    Making the Odoo administrators Team To-Do administrators is a one-off
    seed, not a permanent rule. It is done here instead of with implied_ids
    on base.group_system on purpose: an implication would force every Odoo
    administrator to be a Team To-Do administrator forever, with no way to
    take it away. This way it stays a plain membership that can be changed
    afterwards under Settings > Users.

    Odoo only calls this hook on install, never on upgrade, so a -u does not
    redo the assignment, nor recreate a welcome task that was deleted.
    """
    # In 18.0 the members of a group are in `users` (19.0 renames it to
    # user_ids and adds all_user_ids). Implied memberships are written into
    # `users` too, so this already includes everyone who is an administrator.
    admins = env.ref("base.group_system").users
    if admins:
        env.ref("cimalor_team_todo.group_team_todo_manager").write(
            {"users": [Command.link(user.id) for user in admins]}
        )
    _create_welcome_tasks(env, admins)


def _create_welcome_tasks(env, users):
    """Create one task per administrator explaining how the app works.

    Same pattern as the onboarding to-do of Odoo's own To-Do app: the body is
    a QWeb template rendered in each user's language, so it is translatable
    like any view, and the task itself is the first card to drag to Done.

    Only administrators get it. In a team app a task is work handed over by
    somebody, and a plain user should not find one that nobody assigned.
    mail_auto_subscribe_no_notify keeps the install from sending
    "you have been assigned" notifications.
    """
    vals_list = []
    for user in users.filtered(lambda u: u.active and not u.share):
        env_lang = env(context=dict(env.context, lang=user.lang or env.user.lang))
        body = env_lang["ir.qweb"]._render(
            WELCOME_TEMPLATE,
            {"object": user},
            minimal_qcontext=True,
            raise_if_not_found=False,
        )
        if not body:
            continue
        vals_list.append(
            {
                "name": env_lang._("Welcome to Team To-Do, %s!", user.name),
                "user_id": user.id,
                "description": body,
                "priority": "1",
            }
        )
    if vals_list:
        env["team.todo.task"].with_context(mail_auto_subscribe_no_notify=True).create(
            vals_list
        )
