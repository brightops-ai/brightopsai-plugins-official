# Grok UI Navigation Guide

Playwright-specific instructions for navigating grok.com, managing projects, and interacting with the chat interface. Selectors and patterns verified via live testing.

## URL Patterns

- **Home / Chat:** `https://grok.com`
- **Project page:** `https://grok.com/project/{uuid}?tab=conversations`
- **Chat within project:** `https://grok.com/project/{uuid}?tab=conversations&chat={uuid}`

## Login Detection

After navigating to `https://grok.com`, take a `browser_snapshot`. Signs of a login wall:

- A "Sign in" or "Log in" button is prominent
- No chat input field is visible
- A modal or full-page auth form is displayed

If detected, inform the user and wait for manual login confirmation.

## Finding the Projects Section

The Projects section appears as an expandable button in the left sidebar:

1. Take a `browser_snapshot` — look for `button "Projects" [expanded]` in the sidebar
2. If the sidebar is collapsed, click `button "Toggle Sidebar"` first
3. Projects are listed as links under the Projects button (e.g., `link "ProjectName"`)

If the Projects section is collapsed, click the "Projects" button to expand it.

## Searching for an Existing Project

Once Projects is expanded in the sidebar:

1. Scan the list items for a link matching the target project name
2. Project links have the format: `link "ProjectName"` with URL `/project/{uuid}`
3. Click the matching link to open the project

There is no search/filter input for projects — they are listed directly in the sidebar.

## Creating a New Project (3-Step Dialog)

If the target project is not found:

**Step 1 — Name & Instructions:**
1. Click `button "New Project"` in the projects list
2. A dialog appears with `textbox "Project name"` and `textbox "Project Instructions"`
3. Type the project name (matching the git repo name) into the name field
4. Type adversarial reviewer instructions into the instructions field
5. Click `button "Next"`

**Step 2 — Sources (File Upload):**
1. The dialog advances to "Project Sources" with a drag-and-drop zone
2. Click `button "Attach"` — this opens a dropdown menu (NOT a file chooser directly)
3. Click `menuitem "Upload a file"` from the dropdown
4. The file chooser modal appears — use `browser_file_upload` with the document path
5. Verify the file appears in the dialog with filename and size

**Step 3 — Create:**
1. Click `button "Create"` to finalize the project
2. The page navigates to the new project URL
3. Verify via `browser_snapshot` that the project side panel shows the name, instructions, and source file count

## Uploading Files to an Existing Project

To update or add source files in an existing project:

1. Open the project by clicking its link in the sidebar
2. Look for the Sources section in the project side panel (button labeled "Personal files N")
3. Click it to expand the file list
4. To delete an old file: look for a remove/delete button next to the filename
5. To add a new file: use the Attach button in the sources panel, follow the same Upload flow as project creation

## Chat Input Field

Grok uses a **contenteditable div** (NOT a textarea) for the chat input. The accessibility tree shows it as a `paragraph` with placeholder text "Ask anything".

**To enter text (recommended approach):**

Use `browser_evaluate` to set text directly — this is more reliable than `browser_type` for any prompt over a few hundred characters:

```javascript
() => {
  const editor = document.querySelector('[contenteditable="true"]');
  if (editor) {
    editor.focus();
    editor.textContent = promptText;
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    return 'Prompt set';
  }
  return 'Editor not found';
}
```

**To submit:**

Click the Submit button via `browser_evaluate`:

```javascript
() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const submitBtn = buttons.find(b => b.ariaLabel === 'Submit');
  if (submitBtn && !submitBtn.disabled) {
    submitBtn.click();
    return 'Submitted';
  }
  return 'Submit button not found or disabled';
}
```

After submitting, the URL changes to include `&chat={uuid}&rid={uuid}` — this confirms the message was sent.

## Detecting Response Completion

Grok streams responses in real-time. The **most reliable** detection method is text length stabilization:

1. Wait 15 seconds after submitting
2. Measure response length:
   ```javascript
   () => {
     const els = document.querySelectorAll('.prose, .markdown');
     let len = 0;
     els.forEach(el => { len += el.textContent.length; });
     const submitBtn = Array.from(document.querySelectorAll('button'))
       .find(b => b.ariaLabel === 'Submit');
     return { responseLength: len, submitDisabled: submitBtn?.disabled };
   }
   ```
3. Wait another 15 seconds and measure again
4. If length is unchanged → generation is complete

**Do NOT rely on the Submit button's disabled state.** During testing, the Submit button remained disabled even after Grok finished generating. Text stabilization is the ground truth.

Typical response times for adversarial reviews: 30-60 seconds for a detailed review with 7-10 findings.

## Extracting Response Text

Grok's page contains multiple `.prose` / `.markdown` elements:
- Index 0-1: Usually the user's message (echoed)
- Index 2: May contain "Thought for Xs" thinking indicator
- Index 3: The actual assistant response content

To reliably identify the response:

```javascript
() => {
  const els = document.querySelectorAll('.prose, .markdown');
  const results = [];
  els.forEach((el, i) => {
    results.push({ index: i, length: el.innerText.length, preview: el.innerText.substring(0, 80) });
  });
  return results;
}
```

Then extract the correct element by index:

```javascript
() => {
  const els = document.querySelectorAll('.prose, .markdown');
  return els[3].innerText;  // Adapt index based on enumeration above
}
```

Use the `filename` parameter on `browser_evaluate` to save long responses to a file, then read it with the Read tool.

## Scrolling Long Responses

If the response is longer than the visible viewport:

1. Use `browser_evaluate` to scroll:
   ```javascript
   () => { window.scrollTo(0, document.body.scrollHeight); }
   ```
2. Take a snapshot after scrolling
3. Extract text from the response element (innerText captures the full content regardless of scroll position)

## Timing and Rate Limiting

- Wait 2-3 seconds between navigation actions (clicking, typing)
- Wait at least 1 second after page navigation before taking a snapshot
- If Grok shows a rate limit message ("too many messages", "slow down"), wait 30 seconds and retry once
- If still rate-limited, report to user and suggest waiting

## Common UI Elements to Dismiss

After login, Grok may show various banners that can interfere with navigation:

- **"Connect your X account"** banner — has a `button "Close"` to dismiss
- **"New · Hold Ctrl+D to dictate"** tooltip — has a `button "Dismiss"`
- **"Upgrade to SuperGrok"** heading — appears but doesn't block interaction

These can usually be ignored unless they overlay the chat input. If they do, dismiss them before typing.

## Troubleshooting

If the snapshot shows unexpected state at any point:

1. Take a `browser_take_screenshot` for visual debugging
2. Report what you see to the user
3. Try refreshing: `browser_navigate` back to `https://grok.com`
4. If a popup or modal is blocking, look for a close/dismiss button and click it
