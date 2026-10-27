{
    "name": "Project Status Board",
    "version": "19.0.0.1.0",
    "category": "Services/Project",
    "summary": "Know which projects are moving, waiting or on hold, and why",
    "author": "Cimalor",
    "website": "https://cimalor.com",
    "license": "LGPL-3",
    "depends": ["project", "hr_timesheet"],
    "data": [
        "data/project_project_stage_data.xml",
        "views/project_project_stage_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "application": True,
    "installable": True,
}
