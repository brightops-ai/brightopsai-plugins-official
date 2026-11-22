# Upload gate

Detail for the steps in SKILL.md that stand between a document and grok.com.
SKILL.md holds the rules; this file holds the wording, the inline-fallback
procedure, and cleanup.

## What the gate protects

- **Unscanned content never reaches the transcript or Grok.** Nothing reads
  the document before its snapshot scans clean, and only the snapshot is read
  after that.
- **The bytes approved are the bytes sent.** The snapshot is read-only, in a
  private directory, and identified by its sha256. `check` fails if it was
  altered or the source was saved since.
- **The destination approved is the destination used.** The account and
  project are read from the page and confirmed before anything is created or
  sent, and read again on the sending tab just before each send.

The scripts enforce the snapshot, the scan and `check`. Asking, and stopping
on anything but an explicit yes, are instructions to the agent.

## The questions

Ask each with AskUserQuestion. Fill every placeholder; do not paraphrase the
facts away.

**Before opening Grok (step 4).** Options "Upload" and "Cancel".

> Send `<absolute path of the document>` (sha256 `<first 12 digits>`,
> `<bytes>` bytes) to grok.com, project "<project name>", for review? xAI
> receives the whole file and it cannot be recalled. The secret scan passed;
> that is not a confidentiality check. The account is confirmed with you
> before anything is sent.

**Destination, once the site is open (step 5).** Options "Upload" and
"Cancel". Never skipped.

> Upload to grok.com account "<account as shown on the page>", project
> "<project name>" (<existing, id `<uuid from its link>` | will be created>)?

If the account cannot be read from the page, replace it with "could not be
read from the page — please check the browser window" and have the user name
the account in their answer.

**Re-upload after edits (step 12).** The edited document is new content with
a new sha256. Ask the step 4 question again with the new sha256 and size, and
name the account and project as re-read from the page.

**Inline fallback (step 7).** Options "Paste" and "Cancel". See below.

## Destination re-check

An approval names an account and a project. Between that answer and the
send, the user or the site can switch the active account, and the upload
then lands somewhere nobody approved while the bytes still check out. So
every send — the upload in step 6, the re-upload in step 12, the inline
paste in step 7 — is preceded by this, in this order:

1. On the tab that will send, take a fresh `browser_snapshot`.
2. Re-read the signed-in account from the profile control, and the project
   identifier from the page URL (`/project/{uuid}`). For a project still
   being created there is no identifier yet: read the name in the dialog.
3. Compare both with what the user approved. Same account and same project:
   go on to the byte `check`, then the send.
4. If either differs, or either cannot be read: send nothing. Tell the user
   what the page shows now and ask the step 5 question again. Only a new
   explicit answer for that destination allows the send.

A project created in this run gets its identifier when it is created. Note
it then; later sends compare against it.

## Inline fallback

Grok sometimes cannot read an uploaded project source. Pasting the content
into the prompt sends it through `browser_evaluate` or `browser_type`, which
the skill pre-approves, so the only gate is the user's answer. Make that
answer cover exactly what is sent:

1. **Build the payload first.** Decide what would be pasted: the full
   snapshot content, or the summarised version
   `adversarial-prompt-templates.md` prescribes for a large document. Build
   it from the snapshot, never from the source file.
2. **Full content:** the payload is the approved snapshot. Its sha256 and
   size are already known.
3. **Anything else** (truncated, summarised, a section): the payload is new
   bytes. Give it its own snapshot:
   ```bash
   PAYLOAD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/.adversarial-review-payload.XXXXXX")" && printf '%s\n' "$PAYLOAD_DIR"
   ```
   Write the payload text to a file in that directory, then run
   `snapshot-document.sh create "<payload-file>"` and
   `scan-secrets.sh "<payload-snapshot>" "<document>"`. A hit is a stop.
4. **Ask**, naming the payload and the destination:
   > Grok could not read the uploaded file. Paste <the full content |
   > a truncated version: <which sections are summarised or left out>> of
   > `<absolute path of the document>` (`<bytes>` bytes, sha256
   > `<first 12 digits>`) into the chat at account "<account>", project
   > "<project name>" (id `<uuid>`)? For a truncated version, the exact text
   > is at `<payload-snapshot>`.
5. **On an explicit "Paste":** do the destination re-check above on the
   chat tab, then run `check` on the payload's snapshot as the last command
   before the paste, and paste exactly that snapshot's content.
   For the full content that is
   `check "<snapshot>" "<sha256>" "<document>"`; for a truncated payload,
   `check "<payload-snapshot>" "<payload sha256>" "<payload-file>"`.
6. On any other answer, a destination that differs or cannot be read, or
   any `check` result but `UNCHANGED`, stop.

## Cleanup

Snapshots hold the document's content. Remove them on every way out of the
run, not only at the end: a scan hit, "Cancel", a dismissed question, a
denied upload, a `CHANGED` result, a timeout, an error.

```bash
"${CLAUDE_PLUGIN_ROOT}/skills/adversarial-review/scripts/snapshot-document.sh" remove "<snapshot>"
```

- Run it for each snapshot made in the run, including superseded ones and a
  payload snapshot.
- `remove` deletes that one file and then its directory if empty. `KEPT`
  (exit 1) means something else is in the directory; it is listed and left
  alone.
- For a truncated payload, also remove the working file and its directory:
  `rm -f "<payload-file>" && rmdir "<payload-dir>"`.
