# Build, publication and evidence guide

## Architecture

One project dataset (`data/projects.json`) drives the README browser and details, static website, per-project pages, Atom feed and weekly digest. `data/site.json` controls the editorial date and featured IDs. Counts distinguish core, watchlist and related entries. The site is dependency-free HTML/CSS/JavaScript; building and unit tests require Python 3.12+ only. Browser testing has separate pinned development dependencies.

`id` keeps existing README anchors and site permalinks stable. `first_seen` describes the project's history; `added_at` describes this index's history. Migration recovers catalogue addition dates from full Git history, rather than inventing them. Inherited metadata is preserved, and inherited source-review dates remain unknown until someone reviews the source.

`python3 scripts/catalogue.py build` regenerates outputs. `check` rejects stale committed README/digest output. `validate` checks semantic constraints. The editor schema documents field types; Python additionally checks duplicate records and evidence/availability contradictions.

## Publishing the site

The code and downloadable build are useful before hosting is enabled. **Do not announce a live Pages URL until deployment succeeds.**

The repository owner selects **Settings → Pages → Build and deployment → Source → GitHub Actions**. Then run **Actions → Catalogue integrity → Run workflow**, on `main`. The workflow packages `_site` and deploys only when repository metadata confirms Pages has been enabled. No custom personal access token is needed for ordinary deployments after owner setup.

Intended address: `https://bailo167.github.io/awesome-game-mashups/`. Confirm home, a project permalink, assets, `feed.xml` and `build-info.json`. Only after this readback should `data/site.json` set `site_enabled: true`, followed by regeneration; this controls the README live-site call to action.

Pages enablement is administrative. Committing files does not imply permission to enable Pages. The workflow never tries to bypass that boundary. If enablement is blocked, retain the build artifact and report the owner action.

## Workflows

- **Catalogue integrity:** PRs get read-only validation, unit tests and generated-output checks. Trusted `main` runs can migrate the legacy schema and regenerate committed outputs in a normal non-force-pushed commit. Artifacts record the resulting source commit. A separate read-only Chromium browser job tests HTTP search/filters, URL persistence, mobile layout and no-JavaScript fallback before main-only Pages deployment.
- **Check links:** public reachability audit with no auth headers. Redirect destinations are validated. 2xx = reachable; 404/410 = unavailable; 403/429/timeouts = unresolved. HTTP success does not verify claims. The JSON report retains unresolved URLs rather than hiding them with broad exceptions.
- **Maintenance health:** independent, read-only freshness alarm for the last completed full research cycle. It cannot publish catalogue changes, resume the scheduled maintenance task or override a denied action. See the incident section below.
- Action references are pinned to verified full commit SHAs. Dependabot proposes updates; nothing auto-merges dependency or workflow changes.

Public PR code never runs with a write token, `pull_request_target`, or a private-network runner. Require review for workflows and generators when enabling branch rules; CODEOWNERS alone is review routing.

## Audit findings addressed

The previous README had blank-line breaks inside three tables. Metadata and prose were independently maintained. Demo fields were underused. A global “Last verified” badge obscured per-project uncertainty. The old link checker accepted rate-limit responses as successful checks.

The new implementation generates all views together, surfaces existing demo links, records source-review scope separately from play-testing, and separates reachability from verification. All inherited entries remain present; this structural upgrade does not pretend to re-test every game.

## Research basis, checked 5 October 2026

- [GitHub: custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages): owner enablement, artifacts, deployment dependencies, Pages/OIDC permissions and environments.
- [GitHub: secure workflow use](https://docs.github.com/en/actions/reference/security/secure-use): least privilege, SHA pinning, untrusted PR isolation, CODEOWNERS and Dependabot.
- [W3C WCAG 2.2 reference](https://www.w3.org/WAI/WCAG22/quickref/): keyboard access, visible focus, readable contrast, target sizes and reduced motion. Design guidance, not certification of full WCAG compliance.
- [JSON Schema reference](https://json-schema.org/understanding-json-schema/reference/type): documented record types and machine-readable constraints.
- [Official Awesome submission checklist](https://github.com/sindresorhus/awesome/blob/main/pull_request_template.md): do not promise admission after 30 days. The checklist currently rejects AI-generated material and generated READMEs. This is an independent AI-assisted catalogue, not an official-directory endorsement.

## Completion and checkpoints

A local build, unmerged branch or successful HTTP request is not completion. Publish intended changes to main, read them back, inspect final Actions and record what they checked. Preserve the last genuinely completed research-cycle checkpoint during a structural upgrade or partial recheck. Record a separate structural-upgrade checkpoint instead of rewriting history.

Scheduled research should prioritize missing demos, undocumented requirements, stale reviews and unresolved links, not just project counts.

## Publication incidents and the independent freshness alarm

The GitHub account's push permission, the scheduler's own permission settings and any platform safety review are separate controls. A prompt cannot override the latter. Do not diagnose a generic denial as a token problem, payload-size limit or transient error without evidence. A passing interactive write proves only that particular write succeeded; it does not prove future scheduled writes will succeed. See the incident classification in `.github/CATALOGUE_MAINTENANCE.md`.

The research task must not call scheduler-management tools during execution. Pausing, deleting or changing the task requires a separate maintainer request. This is an instruction, not a technical capability restriction provided by the repository.

The **Maintenance health** workflow runs independently on GitHub, scheduled for 07:15 and 19:15 Australia/Brisbane, and on changes to its code or the checkpoint. It reads only `.github/catalogue-state.json` and `data/projects.json`. The report is uploaded as a 14-day workflow artifact, not committed. GitHub notification delivery depends on the owner's Actions notification settings.

Run locally with:

```sh
python3 scripts/maintenance_health.py
python3 -m unittest discover -s tests -p 'test_maintenance_health.py' -v
```

The default freshness window is two Brisbane calendar days because the historical checkpoint records a date rather than an exact completion time. Exit 0 means only that the recorded full-cycle date is within the window; exit 1 means missing or stale, and exit 2 means invalid input. Recent structural changes, partial reviews and project-count changes do not refresh the full-cycle checkpoint. The script cannot authenticate the truth of a recorded review date.

A red **Maintenance health** result is separate from **Catalogue integrity** or **Check links**. Investigate why research has not completed; never change review dates, thresholds or workflow enablement merely to hide it. The alarm cannot inspect the scheduled task's enablement, restart the task, or guarantee notification delivery. It adds observability; it does not fix or bypass a platform publication denial.

For repeated unexplained platform denials, prepare a private support record with exact messages, times, task ID, affected public paths, before/after commit SHAs and observed permission settings. Keep credentials, private chats and HAR captures out of the public repository. Support investigation and user approval, where required, are separate from routine catalogue maintenance. No support case should be claimed without a confirmed submission.
