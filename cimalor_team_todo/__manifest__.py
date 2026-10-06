{
    "name": "Team To-Do",
    "version": "18.0.2.1.1",
    "category": "Productivity",
    "summary": "Team tasks with shared stages and one owner each",
    "description": """
Shared to-do lists for the whole team, without the Project app: one board,
shared stages, one owner per task, and administrators who see everything.
    """,
    "author": "Cimalor",
    "website": "https://cimalor.com",
    "license": "LGPL-3",
    "depends": ["mail"],
    "images": [
        "static/description/main_screenshot.png",
        "static/description/screenshot_by_person.png",
        "static/description/screenshot_task_form.png",
        "static/description/screenshot_stages.png",
    ],
    "data": [
        "security/cimalor_team_todo_security.xml",
        "security/ir.model.access.csv",
        "data/team_todo_stage_data.xml",
        "data/team_todo_onboarding_templates.xml",
        "views/team_todo_stage_views.xml",
        "views/team_todo_task_views.xml",
        "views/cimalor_team_todo_menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
}
