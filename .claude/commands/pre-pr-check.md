---
description: Run comprehensive pre-PR quality checklist for Mailbox
---

<!-- Adapted from https://github.com/matsengrp/plugins (MIT License) -->

# Pre-PR Quality Checklist

You are helping the user prepare code for a pull request by guiding them through a comprehensive quality checklist.

## Your Role

Guide the user through each step systematically. For each step:

1. Explain what needs to be done
2. Execute the required checks/commands
3. Report the results clearly
4. Only proceed to the next step after the current step passes or the user acknowledges issues

## Checklist Steps

### 1. Issue Compliance Verification (CRITICAL - Do This First!)

- Ask the user for the GitHub issue number they're working on (if applicable)
- Use `gh issue view <number>` to fetch the issue details
- Review ALL requirements in the issue and verify 100% completion
- If any requirement cannot be met, STOP and discuss with the user before proceeding

### 2. Code Quality Foundation

- Run `make quality` (format + lint + typecheck)
- Report any files modified or errors found
- If errors, STOP and require fixes before proceeding

### 3. Documentation, Architecture, and Implementation Reviews

**Documentation Review:**

- Use the Task tool with subagent_type="documentation-reviewer" on all new/modified code
- Check pattern compliance against `docs/*.md`, documentation gaps, clarity issues, update recommendations
- Report findings and wait for the user to address before continuing

**Design Compliance:**

- Confirm the implementation matches the intended design; cross-reference any design doc

**Antipattern Scan:**

- Use the Task tool with subagent_type="antipattern-scanner" on all new/modified code
- Look for SRP violations, silent defaults, error-handling antipatterns, naming issues
- Report findings and wait for the user to address before continuing

**Clean Code Review:**

- Use the Task tool with subagent_type="clean-code-reviewer" on all new/modified code
- Check single responsibility, meaningful names, small functions, DRY
- Report findings and wait for the user to address before continuing

**Code Smell Detection:**

- Use the Task tool with subagent_type="code-smell-detector" on all new/modified code
- Identify maintainability hints and readability improvements
- Report findings for the user's consideration

### 4. Email/API Safety Review (project-specific - CRITICAL)

For any change that sends mail or mutates subscribers/tags in Kit:

- Confirm there is a dry-run path and it was exercised
- Confirm operations are idempotent or guarded against double-send/double-tag
- Confirm `429`/transient errors are handled with backoff and won't cause double-sends
- Confirm no live audience was emailed during testing (a dedicated test segment was used)
- If any of these can't be confirmed, STOP and discuss before proceeding

### 5. Test Quality Validation

- Scan test files for placeholder/`pass`-only tests, unjustified skips, or tests that hit the live API outside `@pytest.mark.integration`
- Confirm HTTP is mocked at the transport boundary per `docs/Testing.md`
- Run `make test` and report pass/fail. If failures exist, STOP and require fixes

### 6. Final Verification

- Run `make precommit` to verify all pre-commit hooks pass
- Report any violations and require fixes

## Success Criteria

All steps must pass before PR creation:

- All issue requirements completed (if applicable)
- `make quality` passes (format + lint + typecheck)
- Code follows documented patterns in `docs/`
- No critical antipatterns (or acknowledged/fixed)
- Email/API safety confirmed for any send/mutation
- All tests passing (`make test`)
- Pre-commit hooks pass (`make precommit`)

## Final Output

After completing all steps, provide:

1. Summary of checklist completion status
2. List of any remaining concerns or warnings
3. Confirmation that code is ready for PR, OR a list of items that need attention

## Important Notes

- **Fail Fast**: Stop at the first major issue
- **Follow the Docs**: All code should follow patterns in `docs/`
- **Sending is irreversible**: Be especially rigorous on the email/API safety step
