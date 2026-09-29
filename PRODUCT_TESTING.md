# Testing through AssureDen

## One-time computer setup

1. Open AssureDen and sign in as an administrator.
2. Open **Admin → Agents → Set up agent**.
3. Download the Windows agent ZIP and extract it. This installer currently
   requires Python 3.14 with Tcl/Tk and Python on PATH, plus Microsoft Edge.
4. Open `Install.cmd`. It installs the companion in your local application-data
   folder, creates a desktop shortcut, and starts it automatically at sign-in.
   Internet access is needed to install its Python dependencies.
5. Enter a computer name in AssureDen and generate a pairing code.
6. In the companion, enter the API server address (`http://127.0.0.1:8000` for a
   local server), paste the code, and select **Pair and connect**. Codes expire
   after ten minutes. Remote API servers must use HTTPS.

The companion stores its credential with Windows DPAPI for the current Windows
user. Keep it open while testing. Routine testing uses the web application;
terminal commands and API documentation are no longer required.

This is a Windows bootstrap installer, not a standalone executable with a
bundled Python runtime. Installation and DPAPI pairing must be checked under
the normal interactive Windows user; the Codex sandbox lacks a loaded DPAPI
user profile.

## Record, review and run

1. Create an application, module and page in Object Repository if needed.
2. Open **Test Cases → Record a test**. Enter a name and application URL,
   select the agent computer, then click **Start recording**.
3. Interact in the Edge window on that computer. Click **Stop and review** in
   AssureDen when finished. The recording uploads directly as a draft. Select
   **Review draft** to open it. No recording-file transfer is needed.
4. Review actions and locators. Choose the destination application/module/page,
   then create the test case. Password inputs become variable placeholders;
   configure the matching secret variables in Environments.
5. Add assertions in the test editor, save the steps, and click **Run test**.
   Choose an environment and a particular agent, or any compatible agent.
6. The run detail page shows progress, steps, assertions, events and artifacts.
   Add a SCREENSHOT step if you want evidence on a successful run.
7. Use **Rerun saved case** to execute the current saved version again. This is
   a fresh run, not replay of the previous immutable snapshot. The Test Runs
   list opens this same detail page.

First acceptance check: produce one passing run, change an assertion to an
incorrect expected value, save, and rerun to confirm a failure is detected.

## Recovery and current limits

- A disconnected agent cannot start a recording. Queued test runs wait for a
  compatible agent. Open the paired companion and check its connection message.
- Use **Discard recording** if recording is abandoned or the companion stopped
  before upload. Discarded recordings cannot later upload a draft.
- A recording reserves that agent against execution claims and expires after
  30 minutes. Only one recording can be active on an agent.
- Capture supports the main tab and top-level document: initial navigation,
  clicks, text changes, single select and checkbox changes. Frames, popups,
  uploads, drag/drop and Enter-key submission remain outside capture coverage.
- Assertions still need authoring after recording. Promotion supports TestCases, reusable Flows and BusinessActions.
- The installer, setup dialog and recording workflow are initial product
  implementations. A clean-machine installer acceptance check remains before
  calling desktop deployment production-ready.

Choose **Create as → Reusable flow** during draft review to preserve the actions as
a versioned flow. Add that flow to test cases through their flow-step controls.

## Reusable business actions

Choose **Business action** when promoting a reviewed draft, or create one under
**Actions & Flows**. Use a meaningful name such as Sign in or Add item to cart.
In the test-case editor, add a FLOW reference and select the business action and
its version. BusinessActions share the canonical step/revision engine with flows;
the library distinguishes their asset type, including on duplicate operations.
Input placeholders use the existing environment/run variables. Dedicated per-call
parameter bindings, outputs and nested action composition are not implemented yet.
