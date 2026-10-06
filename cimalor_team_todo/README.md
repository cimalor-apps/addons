# Team To-Do

Shared to-do lists for the whole team in Odoo 18, without the Project app.

Odoo's own To-Do app is personal: your list, your stages, your board. Team To-Do is for
the team: one board, stages shared by everybody, exactly one owner per task, and an
administrator who sees every task grouped by person.

## Features

- **Shared stages.** A stage belongs to the task, not to the viewer. Moving a card moves it
  for everyone.
- **One owner per task.** The assignee is required and unique. Handing a task over takes it
  away from you.
- **Two roles.** Users see their own tasks and cannot delete them. Administrators see every
  task, can delete, and configure stages.
- **Kanban by stage** with the deadline on the card (red when overdue, orange when due
  today), priority star and owner avatar.
- **List and form** with a clickable stage bar, rich-text description and chatter that
  tracks owner and stage changes.
- **By Person** view for administrators: every task grouped by assignee.
- **Configurable stages**: rename, reorder, fold, and flag closing stages so their tasks
  count as done.
- No dependency on the Project app. An optional companion module,
  `cimalor_team_todo_project`, links tasks to real projects when Project is installed.

## Installation

Standard module installation. The only dependency is `mail` (Discuss).

On install:

- every internal user becomes a Team To-Do **user**, so the app is visible right away;
- the Odoo administrators present at that moment become Team To-Do **administrators**.
  This is a one-off seed, not a permanent rule, so it can be changed afterwards;
- each administrator receives a **welcome task** that explains how the app works. Drag it
  to Done once read, or delete it. It is created only at install, never on upgrade.

## Configuration

- **Roles:** Settings › Users › a user › Access Rights › section _Team To-Do_. A shortcut is
  available under Team To-Do › Configuration › Users & Roles (Odoo administrators only).
- **Stages:** Team To-Do › Configuration › Stages. The stage with the lowest sequence is the
  default for new tasks. Check _Closing Stage_ to have its tasks count as done, and
  _Folded in Kanban_ to collapse its column.

## Usage

- **My Tasks:** your kanban, grouped by stage. Drag a card to change its stage.
- **By Person** (administrators): every task grouped by assignee. Reassign by editing the
  owner; the task disappears from the previous owner's board.
- Filters: _Open_, _Done_, _My Tasks_. Group by assignee or stage.

## Technical notes

- Models: `team.todo.task`, `team.todo.stage`.
- Security: two groups (`group_team_todo_user`, `group_team_todo_manager`), access rights
  in `security/ir.model.access.csv`, and two record rules that filter tasks by owner.
- `is_done` on the task is a stored related field of the stage flag, so it can be filtered
  and grouped on.

### Running the tests

```bash
odoo -d test_db -i cimalor_team_todo --test-enable --test-tags /cimalor_team_todo --stop-after-init
```

### Translations

The template and the Spanish translation live in `i18n/`. Regenerate them with:

```bash
odoo i18n export -d test_db cimalor_team_todo          # .pot
odoo i18n export -d test_db -l es cimalor_team_todo    # es.po
```

## Support

- Email: support@cimalor.com
- Issues: https://github.com/cimalor-apps/addons/issues

We aim to reply to email within 48 to 72 business hours. Issues have no fixed reply time.

## License

LGPL-3. See the `LICENSE` file. Copyright Cimalor, https://cimalor.com.
