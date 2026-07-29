# Curriculum → Classroom (Frappe / ERPNext app)

AI-assisted teaching suite that plugs into the **Frappe Education** module and follows its
structure — **Program → Courses** (a Program has many Courses via Program Course). Everything
teaching-related (**Curriculum, Calendar, Prepare, Library, Homework**) lives *under a Course
inside a Program*. **Timetables are linked to Student Groups.** It pulls in **Academic Years &
Terms, Program Enrollment per term, Students, and Guardians (parents) linked to students**.

It ships a **futuristic web app** at **`/classroom`** (glassmorphism dark UI, role-adaptive)
*and* is fully linked to **Desk** (its own Workspace + all DocTypes editable in Desk).

## Requirements
- Frappe / ERPNext v15+ with the **Education** app installed (`bench get-app education`)
- An Anthropic API key (documents are generated server-side)

## Install
```bash
cd frappe-bench
bench get-app /path/to/curriculum_classroom     # or a git URL
bench --site yoursite.local install-app curriculum_classroom
bench --site yoursite.local migrate
bench restart
```
Then open **Desk → Curriculum Classroom → CC Settings** and set:
- Anthropic API Key (+ model, default `claude-sonnet-4-6`)
- School branding (name, motto, address, logo, accent colour)

Open the web app at **https://yoursite/classroom**.

## Roles & access (created automatically on install)
| Role | What they see in /classroom |
|---|---|
| **CC Super Admin** | Everything: all programs, settings, global KPI dashboard |
| **CC Program Coordinator** | Programs & courses, coverage/performance dashboards, people |
| **CC Teacher** | Their courses: Curriculum, Calendar, Prepare, Library, Homework, Timetables |
| **CC Student** | My dashboard, homework (submit), library materials, my timetable |
| **CC Parent** | Children's performance dashboards & homework status |

Assign a role to a user in Desk (User → Roles). Students/Parents are matched to Education
records by the **user field on Student** and the **email on Guardian**.

## Education data it reads
`Program`, `Program Course`, `Course`, `Academic Year`, `Academic Term`,
`Program Enrollment` (per-term enrollment), `Student`, `Student Group`,
`Student Group Student`, `Guardian`, `Student Guardian`, `Instructor`.

## Custom DocTypes (all visible in Desk)
- **CC Settings** (Single) - API key, branding
- **CC Curriculum** (+ child **CC Curriculum Topic**) - per Program+Course+Year/Term, file + AI-extracted topics with week/term/planned date/status
- **CC Lesson** (+ child **CC Lesson Material**) - the Library: generated Lesson Plan, Teacher's/Lesson/Student Notes & Assessment filed under Term → Week → Topic, plus reading materials (files of any type or links)
- **CC Homework** / **CC Homework Submission** - assignments per course & student group, AI grading
- **CC Timetable** (+ child **CC Timetable Slot**) - weekly grid **per Student Group**, slots link to Course + curriculum topic + prepared Lesson

## Structure
```
curriculum_classroom/
├── hooks.py                  # routes /classroom, install hook, workspace
├── setup/install.py          # creates the 5 CC roles + Desk workspace
├── api/api.py                # whitelisted REST endpoints (all portal traffic)
├── curriculum_classroom/doctype/…   # DocTypes above
└── www/classroom/            # the single-page web app (index.html + index.py)
```

## Notes
- All AI calls run server-side (`api._claude`) using the key in CC Settings; nothing is exposed to the browser.
- If the Education app is missing, the portal still loads and tells you what to install.
- KPI dashboards are computed per-role in `api.dashboard`.
