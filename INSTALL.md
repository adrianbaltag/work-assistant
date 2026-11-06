# Install guide

A short, step-by-step guide to install Work Assistant, start it, and keep it up to date.
Each step shows **Windows** first, then **Mac**. Do only the one for your laptop.

The app runs only on your own laptop, at http://127.0.0.1:5050. Nothing is uploaded.

For more detail (Slack, the work_jira hooks, fixing errors) see [README.md](README.md).

---

## Before you start

You need:

- **Python 3.10 or newer**
- **Git**
- The **VPN**, if you're not in the office

Check both. If a line prints a version number, you have it.

Windows (PowerShell: Start menu, type "PowerShell"):

```powershell
python --version
git --version
```

Mac (Terminal: Cmd+Space, type "Terminal"):

```bash
python3 --version
git --version
```

---

## Part 1: Install (once, about 10 minutes)

### Step 1: Download the app

Windows:

```powershell
cd $HOME\Desktop
git clone https://github.com/adrianbaltag/work-assistant.git
```

Mac:

```bash
cd ~/Desktop
git clone https://github.com/adrianbaltag/work-assistant.git
```

You now have a `work-assistant` folder on your Desktop.

### Step 2: Install the app's packages

This makes `.venv`, a private copy of Python only for this app, and installs what it needs into it.

Windows:

```powershell
cd $HOME\Desktop\work-assistant
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

If `python` is not found, use `py` instead in the second line.

Mac:

```bash
cd ~/Desktop/work-assistant
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
```

### Step 3: Make your settings file

The settings file tells the app where your folders are.

**Where:** in the same PowerShell (Mac: Terminal) window you used for Step 2. It is already inside
the `work-assistant` folder. If you closed it, open a new one and run `cd $HOME\Desktop\work-assistant`
first (Mac: `cd ~/Desktop/work-assistant`).

**How:** paste one line, press **Enter**, then the next line.

**1. Make your own copy of the example file and open it.**

Windows:

```powershell
copy settings.ini.example settings.ini
notepad settings.ini
```

Mac:

```bash
cp settings.ini.example settings.ini
open -e settings.ini
```

The first line makes `settings.ini` (prints nothing, that's normal). The second opens it in
Notepad (Mac: TextEdit).

**2. Change 3 lines in the file.** Lines that start with `#` are notes: leave them. On each line below,
change only the part after `=`. No spaces around `=`, no quotes.

| Line | What to put | Needed? |
|---|---|---|
| `projects_folder=` | The folder for your project notes. Windows: `C:\Users\YOUR-NAME\Desktop\projects`. Mac: `/Users/YOUR-NAME/Desktop/projects`. | Yes |
| `jira_url=` | Open any Jira ticket and copy the address **before** `/browse/`. | For the **Open in Jira** button |
| `work_jira_folder=` | Your `work_jira` folder, for example `C:\Users\YOUR-NAME\Desktop\work_jira`. Leave it as it is if you don't have one. | For **Work project** folders |

`YOUR-NAME` = your user name on the laptop. Not sure? Run `echo $HOME` in the window: it prints
`C:\Users\<your name>` (Mac: `/Users/<your name>`).

**3. Save and close.** Press **Ctrl+S** (Mac: **Cmd+S**), then close Notepad (TextEdit).
`settings.ini` stays on your laptop and is never uploaded.

**4. Make the projects folder** if it doesn't exist yet (back in the PowerShell or Terminal window):

Windows:

```powershell
mkdir $HOME\Desktop\projects
```

Mac:

```bash
mkdir ~/Desktop/projects
```

If you used a different folder in step 2, use that path instead. "Already exists" = fine, you have it.

### Step 4: Check your Claude login

Open a **new** PowerShell or Terminal window and run:

Windows:

```powershell
echo $env:ANTHROPIC_BASE_URL
```

Mac:

```bash
echo $ANTHROPIC_BASE_URL
```

- **It prints an address:** your login is already set. Nothing to do.
- **It prints nothing:** you'll type it in each time you start the app (Part 2, step 2).
  Ask your team lead for the gateway address and your token.

### Step 5 (optional): Slack and work_jira

You can skip both. The app works without them.

- **Slack button:** README.md, "Part 1, Step 5".
- **Cards that follow your work_jira folders:** README.md, "Sync with work_jira", then "Set it up (once)".

---

## Part 2: Start the app (every time)

**1. Go to the app folder.**

Windows:

```powershell
cd $HOME\Desktop\work-assistant
```

Mac:

```bash
cd ~/Desktop/work-assistant
```

**2. Set your login. Skip this if Part 1, Step 4 printed an address.**
Run each line on its own, paste when asked, press Enter.

Windows:

```powershell
$env:ANTHROPIC_BASE_URL = Read-Host "Paste the Claude gateway address"
$env:ANTHROPIC_AUTH_TOKEN = Read-Host "Paste your Claude token"
```

Mac (the second line shows nothing while you paste. That's normal.):

```bash
read ANTHROPIC_BASE_URL && export ANTHROPIC_BASE_URL
read -s ANTHROPIC_AUTH_TOKEN && export ANTHROPIC_AUTH_TOKEN
```

Your login is kept only in this window. Close it and it's gone, so nothing secret is saved on disk.

**3. Check everything (about 10 seconds).**

Windows:

```powershell
.venv\Scripts\python check_setup.py
```

Mac:

```bash
.venv/bin/python3 check_setup.py
```

Every line should say `[ OK ]` or `[SKIP]`. A `[FAIL]` line says what to fix.

**4. Start the app.**

Windows:

```powershell
.venv\Scripts\python app.py
```

Mac:

```bash
.venv/bin/python3 app.py
```

Open http://127.0.0.1:5050 in your browser. **Keep the window open** while you use the app.
To stop the app: click the window and press **Ctrl+C**.

---

## Part 3: Get the newest version

**1. Stop the app** (Ctrl+C in its window), then close that window.

**2. Open a new window and update.**

Windows:

```powershell
cd $HOME\Desktop\work-assistant
git pull
.venv\Scripts\python -m pip install -r requirements.txt
```

Mac:

```bash
cd ~/Desktop/work-assistant
git pull
.venv/bin/python3 -m pip install -r requirements.txt
```

**3. Start the app** as in Part 2. If the page still looks old, press **Ctrl+F5** (Mac: **Cmd+Shift+R**).

Your `settings.ini` and your project notes are never touched by an update.

If `git pull` says **"Your local changes would be overwritten"**, stop. A file in the app folder
was changed on your laptop. Don't delete anything. Ask for help.

---

## Part 4: A new work project, start to finish

You need `work_jira_folder=` in `settings.ini` and the hooks set up (Part 1, Step 5).

1. **Dashboard:** click **+ New project**. Tick **Work project**. Type the ID (for example `ABC-123`),
   a title, and paste the Jira description. The app makes the card and the folder
   `work_jira\ABC-123\`, with a `ticket.md` inside.
2. **Start Claude inside that folder.** Use the project folder itself, never all of `work_jira`:

   Windows:

   ```powershell
   cd $HOME\Desktop\work_jira\ABC-123
   claude
   ```

   Mac:

   ```bash
   cd ~/Desktop/work_jira/ABC-123
   claude
   ```

   (In VS Code: File → Open Folder → the project folder, then start Claude.)
3. **First session: setup.** Type `set up this project`. Claude copies the tracking files from
   `_templates`, reads `ticket.md`, then stops and asks you to start a new session.
4. **Second session: requirements.** Type `/clear`. Claude offers **clear-requirements**, then **grill-me**.
   Answer its questions. At the end it writes the milestones (M1, M2, …) in `requirements.md`.
   It also offers local git once. Say yes.
5. **Every session after that: one milestone.** Claude works on one milestone, ticks it, updates
   `tracking_log.md`, then stops. The dashboard card updates by itself.
6. **Finished?** Move the folder out of `work_jira`. Next time Claude starts, the card moves to the
   Archive page by itself.

---

## Something wrong?

- Run the check: `.venv\Scripts\python check_setup.py` (Mac: `.venv/bin/python3 check_setup.py`).
  It says what to fix and never shows your tokens, so it's safe to show a colleague.
- Then see the "Something went wrong" table in README.md.
