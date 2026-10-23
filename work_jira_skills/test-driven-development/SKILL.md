---
name: test-driven-development
description: Use in Phase 3-Build of a work_jira ticket when writing or changing any function in the prod script, or fixing a bug - write the failing pytest first, watch it fail, then the smallest code that passes. Adapted from obra/superpowers (MIT, © 2025 Jesse Vincent).
---

# Test-Driven Development (work_jira)

## Overview

Write the test first. Watch it fail. Write the smallest code that passes.

**Core principle:** if you never saw the test fail, you don't know it tests the right thing.

## The rule

```
NO PROD-SCRIPT CODE WITHOUT A FAILING TEST FIRST
```

Wrote code before its test? Delete it and start again from the test. Don't keep it "as reference".

**Skip only with the user's OK:** throwaway exploration in a scratch file, config, SQL run by hand in
Beaver, and steps the milestone marks `user check` (Spyder run, review, prod).

## The cycle, one behavior at a time

1. **RED: write one test** in `tests/` for one behavior, named after it.
   ```python
   def test_skips_blank_rows(tmp_path):
       sheet = make_sheet(tmp_path, rows=[["S001", "NE"], ["", ""], ["S002", "SW"]])
       assert [s["site_id"] for s in read_sites(sheet)] == ["S001", "S002"]
   ```
   Use real code and small sample files (`tmp_path`, `tests/data/`). Never read Z:, Y: or live
   servers in a test: build a tiny copy of the data instead.
2. **Watch it fail:** `python -m pytest tests -v`.
   It must FAIL (assert or missing function), not ERROR (typo, bad import). Passes already? You are
   testing old behavior: change the test.
3. **GREEN: smallest code** that makes it pass, in the prod script's own `# %%` cell. Nothing extra
   (no options "for later").
4. **Watch it pass:** run the WHOLE suite, not just the new test. Every failure goes in your
   report by name, even one you didn't cause.
5. **Clean up** (names, duplication) with the suite still green. No new behavior here.
6. Next behavior → back to 1.

## Bug fixes

First a test that reproduces the bug and fails. Then the fix. The test stays, so the bug can't come back.
Use systematic-debugging to find the cause before you fix.

## Prod script reminders

- Code that runs on import (reading files, connecting) goes under `if __name__ == "__main__":`, so
  pytest can import the script safely.
- `test=True` is for the user's Spyder run, not a pytest shortcut: pytest calls the functions directly.

## Red flags: stop and start over

- Code written before its test
- A new test that passed the first time you ran it
- You can't say why the test failed
- "Too simple to test", "I'll add tests after", "I already tried it by hand"

## Before saying the milestone's tests are done

- [ ] Every new function has a test
- [ ] You saw each test fail for the right reason first
- [ ] Whole suite green, output clean (no errors or warnings)
- [ ] The tests named in the milestone's `Done when:` exist and pass

Then use verification-before-completion before ticking anything.
