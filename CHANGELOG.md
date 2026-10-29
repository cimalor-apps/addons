# Changelog

All notable changes to the Cimalor modules for Odoo 18.0 and 19.0. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the Odoo Apps Store
convention `<series>.<major>.<minor>.<patch>`, where the series (`18.0` or `19.0`) matches the
Odoo version. The same functional version number means the same features in both series.

## cimalor_team_todo — Team To-Do

### [18.0.2.1.1] - 2026-10-06

#### Changed

- Same changes as 19.0.2.1.1: support address `support@cimalor.com` in the welcome task
  (existing databases keep the old one, by design), and the reply-time wording of the Store
  page and README, which now applies to email only.

### [19.0.2.1.1] - 2026-10-06

#### Changed

- Support address in the welcome task is now `support@cimalor.com` (was
  `soporte@cimalor.com`). The task is created only on install from a `noupdate` template,
  so databases that already have it keep the old address: it is content the administrator
  may have edited, and an upgrade does not rewrite it.
- Store page and README: support at `support@cimalor.com`. "We aim to reply within 48 to 72
  business hours" applies to email only; GitHub issues have no fixed reply time.

### [18.0.2.1.0] - 2026-09-29

#### Added

- First release for Odoo 18.0, with the same features as 19.0.2.1.0.

#### Changed (differences from 19.0)

- Roles hang from the `Team To-Do` module category through `category_id`, because
  `res.groups.privilege` does not exist in 18.0. The user form shows them as a User /
  Administrator selector under _Other_.
- The install hook reads and writes group members through `users` instead of `user_ids` and
  `all_user_ids`.

### [19.0.2.1.0] - 2026-09-09

#### Added

- Welcome task for each administrator on install, explaining shared stages, single
  ownership, roles and where to configure things. Same pattern as the onboarding to-do of
  Odoo's To-Do app: QWeb template rendered in the user's language, no notification sent,
  created only at install.

### [19.0.2.0.0] - 2026-09-09

#### Changed

- **Renamed** the module from `todo_team` to `cimalor_team_todo` and the display name from
  "ToDo Team" to "Team To-Do". Models are now `team.todo.task` and `team.todo.stage`. The
  previous name was never published, so there is no migration path from it.
- **One owner per task.** `user_id` replaces the former multiple assignees and is required.
  Reassigning a task removes it from the previous owner's board.
- Deadline shown on the kanban card with the `remaining_days` widget: red when overdue,
  orange when due today, hidden once the task is done.
- Manifest signature: author `Cimalor`, website `https://cimalor.com`.

#### Added

- Store listing: icon, description page (`static/description/index.html`) and screenshots.
- `README.md` for the module.

### [19.0.1.0.0] - 2026-08-31

- First version, as `todo_team`: team tasks with shared stages and several assignees, user
  and administrator roles, record rules, default stages, kanban/list/form views, Spanish
  translation and tests.

## cimalor_team_todo_project — Team To-Do: Project link

### [18.0.1.1.0] - 2026-09-29

#### Added

- First release for Odoo 18.0, with the same features as 19.0.1.1.0.

#### Fixed (difference from 19.0)

- The project link on the kanban card sets `active_id` to the project before returning the
  action of the Project app. In 18.0 that action does not set it, and the web client fills it
  with the team task, so the list would have been filtered by the wrong project.

### [19.0.1.1.0] - 2026-09-09

#### Added

- The project name on the kanban card is a link that opens the task list of that project
  (`action_open_project_tasks`, delegating to the Project app).
- Project field in the search view and _Project_ group-by.
- Store listing: icon, description page and screenshot. `README.md` for the module.

#### Changed

- **Renamed** from `todo_team_project` to `cimalor_team_todo_project`; display name
  "Team To-Do: Project link".

### [19.0.1.0.0] - 2026-08-31

- First version, as `todo_team_project`: optional `project_id` on team tasks, shown on the
  form, list and kanban; auto-installed when the Project app is present.

## cimalor_project_status_board — Project Status Board

### [19.0.0.1.0] - Unreleased

#### Added

- Board of projects by lifecycle state on Project's own stages. Each stage gets a state
  type (To Start, In Progress, Waiting, On Hold, Done); the four native stages are typed on
  install and two stages are added, Waiting and On Hold (folded).
- Waiting and On Hold ask for a reason, who the project depends on (customer, supplier or
  us), a follow-up or restart date and, for catch-all reasons, a note. Required on the
  project form only, so dragging a card is never blocked: the card is flagged instead.
- Ten starting reasons, editable under Configuration › Reasons.
- History of every state change (`cimalor.project.state.log`), read and create only, and a
  chatter note when a project starts waiting or goes on hold.
- Project form with the state as buttons, the state sentence, and the main tasks as a
  to-do list with planned and spent hours. Ticking a task closes it through its state and
  never touches its planned hours.
- Spanish translation.

#### Notes

- Installing turns on Project's _Project Stages_ setting; uninstalling does not turn it off.
- Project users get write access to projects (not create or delete), limited by Project's
  own record rules, so they can change the state of the projects they see.
- On uninstall, Waiting and On Hold are deleted only when no project is in them; a stage in
  use stays as an ordinary Project stage.
- Depends on `project` and `hr_timesheet`. Projects created before the install have no
  history until their first state change.
