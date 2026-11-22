# Project Status Board

Know which projects are moving, waiting or on hold, and why. For Odoo 19 with the Project
and Timesheets apps.

Project's stages tell you where a project is, not why it is stuck. Project Status Board turns
the stages into a board of states and asks for the missing piece when a project stops: what
it is waiting for, who it depends on and when to chase it again.

## Features

- **A board of projects by state:** To Start, In Progress, Waiting, On Hold and Done. Drag a
  card to change its state. On Hold is folded, so long pauses stay out of the way.
- **Waiting and On Hold ask for their data:** a reason and a follow-up or restart date. A
  Waiting project always waits on the customer; On Hold also records who it depends on
  (customer, supplier or us). A card dragged without its data is flagged until somebody
  fills it in.
- **The state sentence on every card**, such as _Since 23/10/2026: Approval of a delivery_
  in the Waiting column or _Until 15/01/2027: Customer postpones_ for On Hold, with the
  follow-up date in red once it has passed.
- **A project form for day-to-day work:** the state as a row of buttons, the main tasks as a
  to-do list with planned and spent hours, and the closed ones apart. Ticking a task closes
  it without touching its planned hours.
- **A timer on every task:** press play in the task list and a live counter starts; stop it
  to log the time as a standard timesheet line, with a required comment. One timer per
  person: pressing play on another task first asks for the running one's comment.
- **The last comment on every card:** "Ana · 12/11 · comment" (first name and day/month)
  of the project's latest timesheet comment, on one line under the state, whoever logged
  it and from wherever. Project name and customer take one line each, cut if too long.
- **History of every state change:** who, when, the reason and the dates, never rewritten.
  The chatter gets a note each time a project starts waiting or goes on hold.
- **Configurable reasons**, ten to start with; On Hold ones propose who the project depends
  on.
- **Hours margin on every card and form:** allocated hours left minus the pending work of
  the open main tasks (planned minus spent, never below zero). Red over budget, amber tight
  (under 10 % of the allocated hours), green with room; grey without allocated hours.
- **Days margin on every card and form:** each person works through their tasks by due
  date at their daily capacity; the project's forecast end is when its last open task ends,
  and the margin is the working days to the delivery date. Red late (with who it is late
  because of), amber two days or less, green on time; grey without delivery date or when
  somebody has no working schedule. Board filters _Over Budget_, _Hours at Risk_, _Late_
  and _Date at Risk_.
- **Reporting:** _Workload_ (pending hours by person, project stage and due date),
  _Capacity_ (daily and weekly capacity, weeks of work and queue end per person),
  _Queue by Person_ (a timeline of each person's queue: one row per project in the order
  they reach it, red when their part ends after the project's delivery date, which is
  marked),
  _Date Risk_ (projects at risk) and _Team Activity_ (what each person is on now, from
  their running timer, and the hours they logged by project over the last five working
  days, at most five projects each). State changes are still logged in each project's
  chatter.
- Uses Project's own stages and tasks: no parallel data model, and the Project app keeps
  working exactly as before.

## Installation

Standard module installation. Dependencies: `project` and `hr_timesheet`.

On install the module:

- turns on the **Project Stages** setting of Project, which the board needs. Uninstalling
  does not turn it off: untick it under Project › Configuration › Settings if you want to;
- gives Project's four stages a state type (To Do: To Start, In Progress: In Progress,
  Done and Cancelled: Done) and adds two stages, **Waiting** and **On Hold**;
- loads ten starting reasons.

Projects created before the install have no history yet: it starts with their first state
change.

On uninstall, Waiting and On Hold are deleted only if no project (archived ones included)
is in them. A stage that still holds projects stays as an ordinary Project stage, so no
project loses its column. If you reinstall afterwards, the module adds a new Waiting or On
Hold stage next to the one that stayed: move the projects and delete the old one.

## Configuration

- **Reasons:** Project Status Board › Configuration › Reasons. The Configuration menu is for
  Odoo administrators only; Project administrators can still manage reasons. Each
  reason is used for Waiting or for On Hold and can require a note (as _Other_ does). On
  Hold reasons also propose who the project depends on.
- **Stages:** Project Status Board › Configuration › Stages, which is Project's own stage
  list. Set the **State Type** of each stage; a stage without a type is shown but gets no
  special behaviour. Several stages may share a type.
- **Capacity:** each person needs a user linked to an employee with a working schedule. The
  **Daily Admin Time** next to the schedule, on the employee's _Payroll_ page (1
  hour by default), is subtracted from each working day. Approved time off and public
  holidays are taken into account through Odoo's resource leaves.
- **Margins:** give projects their allocated hours and delivery date, and tasks their
  planned hours. Tasks without planned hours count zero.
- **Excluded projects:** Project › Configuration › Settings › Project Status Board (Odoo
  administrators; also under the app's Configuration › Settings). A filter on projects,
  with Odoo's domain editor: projects matching it, such as hour banks, are left out of the
  boards, the reports and everybody's workload. They stay untouched in Project. The
  filter is applied when saved, when projects change, and once a day.
- **Excluded tasks and hour banks:** in the same place, a filter on tasks. Matching tasks,
  such as the ones holding an hour bank's balance, never count as work. A project with
  such tasks is an **hour bank**: each customer request is a task of its own, and only
  requests count (pending work, workload, queue, days margin). Its hours margin is the
  requests' estimate minus their time: green, or red once a request goes over. Without
  open requests the bank goes **on hold by itself** (reason _Hour bank without
  requests_, no date needed) and comes back to In Progress with the next request, with a
  note in the chatter each time. A bank put on hold by hand for another reason is left
  alone.
- **Reasons without date:** a reason can say it needs no follow-up or restart date
  (_Requires Date_), so its projects are not flagged as missing data.
- **Employees left out of the reports:** in the same place, a list of employees with a
  user (such as managers who do not log project work) who do not appear in Team
  Activity, Workload, Capacity, Queue by Person or the daily email. Their tasks still
  count for the projects' margins. The list only trims the views of Project
  administrators: a person who only sees themselves keeps seeing themselves. One list
  per company.
- **Daily email:** in the same place, the recipients and the time of the next email; it
  then repeats every day at that time (the scheduled action _Project Status Board: daily
  email_). It holds the team activity, the projects at risk and the overdue follow-ups.
  Project administrators get the whole team and every project they see; anybody else
  gets their own activity and their own projects (the ones they manage or have tasks
  in, as in My Projects). It goes out through the database's outgoing mail server, like
  any other Odoo email: set one up first.

## Usage

- **Projects › My Projects:** the board with the projects you manage or have tasks in; the
  app opens here. **All Projects** shows every project you can see. Drag a card to change
  its state; clicking it opens the project form.
- **Waiting / On Hold:** choose the reason and the date in the form. Waiting always depends
  on the customer and does not ask; for On Hold, who the project depends on is proposed by
  the reason and can be changed.
- **Tasks tab:** tick a task to close it, untick it in _Closed Tasks_ to reopen it. Add
  tasks with or without planned hours, and drag the handle to change their order.
- **Timer:** press ▷ on a task to start, ■ to stop. The dialog proposes the elapsed time
  (rounded to the minute), which you can correct, and asks what you did: the comment is
  required and becomes the card's last comment. _Keep Running_ closes it without stopping.
  Under a minute, one minute is logged, so the comment is never lost. While anybody times
  a task of a project, its card shows a green dot top right (who, on hover). Logging time
  needs your user to be linked to an
  employee, and the Timesheets user right. The comment is required only in this dialog:
  timesheets from the Timesheets app or imports keep their own rules.
- **State History tab:** every change of state with its author and data.

## Access rights

Project **users** can change the state of the projects they **manage or have tasks in**
(closed tasks count too), which means writing on those projects (not creating or deleting
them). They still see every project Project lets them see, but cannot move the others.
When somebody other than the project manager changes the state, the manager gets a
_Project State Changed_ activity, refreshed on later changes instead of piling up.
Project **administrators** change any project and also manage the reasons.

## Technical notes

- Models: `cimalor.project.state.log` (history, read and create only),
  `cimalor.project.stop.reason`, `cimalor.project.timer` (running timers, each user sees
  only their own) and the `cimalor.project.timer.stop` dialog; the read-only reports
  `cimalor.project.workload.report` (a database view) and `cimalor.project.capacity.report`;
  `cimalor.project.queue`, the per-person work queue behind the capacity and the days
  margin; extensions of `project.project`, `project.project.stage`, `project.task` and
  `hr.employee`.
- _Queue by Person_ is a small OWL client action of the module
  (`static/src/queue_timeline/`): Odoo's Gantt view is Enterprise. It reads
  `cimalor.project.queue.get_timeline_data()`, with the user's own rights.
- _Team Activity_ is another client action (`static/src/team_activity/`), fed by
  `cimalor.project.activity.get_activity_data()`: it picks the people first (oneself, or
  every Project user with an employee for Project administrators), then reads their
  timers and timesheets as superuser, since timers are private to their user.
- The daily email (`cimalor.project.digest`) reads the same data as each recipient
  (`with_user`) and renders a QWeb template of tables with inline styles
  (`views/cimalor_project_digest_templates.xml`): mail clients run no JavaScript and keep
  little CSS, so it cannot reuse the OWL view. The lists of people live on the company
  (`res.company`) and are edited in the settings through related fields.
- The days margin is computed when read, never stored: it depends on the other projects of
  the same people, which `@api.depends` cannot follow.
- The live counter is the module's only JavaScript: the `cimalor_timer` field widget, which
  shows "now minus start" every second, so it stays right after the computer sleeps.
- The state type lives on the stage (`cimalor_state_type`); every rule reads it, never the
  stage name nor `fold`.
- `project.project.write()` is the single entry point of the history: the form, the kanban
  drag, imports and the API all log there.
- The board and the form are new views with priority 100, used only by this app's action,
  so Project's default views are unchanged.

### Running the tests

```bash
odoo -d test_db -i cimalor_project_status_board --test-enable --test-tags /cimalor_project_status_board --stop-after-init
```

### Translations

The template and the Spanish translation live in `i18n/`. Regenerate the template with:

```bash
odoo i18n export -d test_db -l pot -o cimalor_project_status_board.pot cimalor_project_status_board
```

Merge the new entries into `i18n/es.po` by hand instead of overwriting it: the export drops
translations that equal their source text and the `Language`/`Plural-Forms` header.

## Support

- Email: support@cimalor.com
- Issues: https://github.com/cimalor-apps/addons/issues

We aim to reply to email within 48 to 72 business hours. Issues have no fixed reply time.

## License

LGPL-3. See the `LICENSE` file. Copyright Cimalor, https://cimalor.com.
