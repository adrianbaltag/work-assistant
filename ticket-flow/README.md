# ticket-flow (Claude Code plugin)

From a vague ticket to a clear, confirmed problem, then milestones built one per session.
One plugin holds the skills, the code reviewer and the hooks, so there is one thing to install.

**Not ready yet.** The three skills and the reviewer are written, but the hooks are not in yet
and nothing was tried on a real ticket. Do not install it for real work.

| Part | What it does |
|---|---|
| `clear-ticket` (skill) | From a vague ticket to a real issue the creator said yes to. |
| `plan-milestones` (skill) | Cuts the confirmed ticket into milestones, each with a proof. |
| `build-milestone` (skill) | Builds one milestone per session: test, code, proof, review, tick. |
| `code-reviewer` (agent) | Strict and read-only. Reviews each code milestone before it is ticked. |
| `hello` (skill) and one hook | Only for the install test below. |

## The 5-minute install test (Windows PowerShell)

This only checks that a plugin can be installed on your laptop. It changes nothing in your
projects. Do the steps in order. If a step shows an error, stop there and keep the error text.

**1. Which Claude Code is this?**

```powershell
claude --version
```

**2. Does it know plugins?** You should see a list of commands (install, marketplace, validate).

```powershell
claude plugin --help
```

**3. Get the test branch.**

```powershell
cd $HOME\Desktop\work-assistant
git fetch
git switch feat/v2-plugin
git pull
```

**4. Check the plugin files.** Last line should say `Validation passed`.

```powershell
claude plugin validate ./ticket-flow
```

**5. Try it for one session only** (nothing is installed).

```powershell
claude --plugin-dir ./ticket-flow
```

When Claude starts, look for a line that begins with `PLUGIN-TEST`. Then type:

```
plugin hello
```

Claude should answer `ticket-flow: the hello skill works.` Then type:

```
Copy the line in your context that starts with PLUGIN-TEST, word for word.
```

Keep that line. Type `/exit` to leave.

**6. Install it for real.**

```powershell
claude plugin marketplace add ./
claude plugin install ticket-flow@work-assistant
claude
```

Do the same two checks as in step 5 (`plugin hello`, then the PLUGIN-TEST line). Keep this
second PLUGIN-TEST line too: it will be different from the first one. Type `/exit`.

**7. Take it out again and go back to the main branch.**

```powershell
claude plugin uninstall ticket-flow@work-assistant
claude plugin marketplace remove work-assistant
git switch main
```

### What to bring back

- the version from step 1
- the two PLUGIN-TEST lines (steps 5 and 6)
- the text of any error, and the step it came from. A message like
  `blocked by enterprise policy` means the company switched plugins off: that is a useful
  answer too.
