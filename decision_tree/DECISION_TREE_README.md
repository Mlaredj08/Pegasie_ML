# Decision Tree Runner - Complete User Guide

## Overview

The **Decision Tree Runner** is a web-based questionnaire engine that executes pre-built decision trees. It allows users to navigate through branching questionnaires, answer questions of various types, and generate structured profile outputs. This module is designed to **run** decision trees created with the [Decision Tree Editor](\EDITOR_README.md).

## Accessing the Runner

1. **Login** to the JFIP web application
2. Navigate to the **Dashboard** (main menu)
3. In the **Experimental Zone** section, click **"Decision Tree"**
4. The runner opens at `/questionnarie_decision_tree`

---

# Section 1: User Interface Guide

## Interface Layout

The Decision Tree Runner has three main stages:

### Stage 1: Start Screen

The initial screen where you select and configure your questionnaire session.

#### Tree Selection Panel

| Element | Description |
|---------|-------------|
| **Tree Source Dropdown** | Select from available decision tree JSON files |
| **Available Trees List** | Shows all trees in the `decision_tree/trees/` folder with clickable links and delete buttons |
| **Start Button** | Begins the questionnaire with the selected tree |
| **Home Button** | Returns to the main JFIP Dashboard |

#### CSV Upload Panel

| Element | Description |
|---------|-------------|
| **CSV File Input** | Upload a CSV file to convert into a decision tree |
| **Saved JSON Name** | Filename for the converted tree (auto-appends `.json`) |
| **Start Node** | Optional - specify which node ID starts the questionnaire |
| **Convert & Save** | Converts CSV to JSON and saves to trees folder |
| **Select Uploaded Tree** | Quickly select the just-uploaded tree |
| **Server Response Preview** | Shows the converted JSON structure |

#### Testing / Debug Panel

| Element | Description |
|---------|-------------|
| **Debug Answers Textarea** | Paste a JSON map of `{ node_id: answer }` to auto-fill answers |
| **Answering User** | Username for auto-run mode (default: "debug") |
| **Start (auto-run)** | Starts questionnaire and auto-answers from debug JSON |
| **Render Finish with Payload** | Jumps directly to finish screen with provided payload |

---

### Stage 2: Questions Screen

The main questionnaire interface where users answer questions.

#### Progress Bar

- **Visual Bar**: Shows percentage completion
- **Question Index**: Displays current position (e.g., `3/10`)

#### Question Display

| Element | Description |
|---------|-------------|
| **Question Prompt** | The question text (may include template variables like `{{answers.previous_node}}`) |
| **Node Metadata** | Shows node ID and type (e.g., `Node: user_name · Type: text`) |
| **Input Field** | Appropriate input based on question type |

#### Question Types & Inputs

| Type | Input Control | Description |
|------|---------------|-------------|
| **yes_no** | Two toggle buttons (Yes/No) | Binary choice returning `true`/`false` |
| **text** | Textarea | Free-form text input |
| **list** | Text input with comma parsing | Comma-separated items converted to array |
| **single_select** | Dropdown menu | Choose one from predefined options |
| **multi_select** | Checkbox buttons | Choose multiple from predefined options |

#### User Selection Bar

| Element | Description |
|---------|-------------|
| **User Dropdown** | Select the answering user from registered users |
| **Add User Input** | Format: `Name, Role` to add a new user |
| **Add Button** | Registers the new user for this session |

#### Navigation Controls

| Button | Function |
|--------|----------|
| **← Back** | Return to previous question (rewinds session) |
| **Skip** | Skip current question with default/empty answer |
| **Next** | Submit answer and proceed to next question |
| **Finish** | Appears on end nodes - proceed to review screen |

---

### Stage 3: Finish Screen

The review and submission screen.

#### Answers Preview

- **JSON Preview**: Formatted display of all collected answers and generated profile
- **Scrollable container** for large answer sets

#### Action Buttons

| Button | Function |
|--------|----------|
| **Ask AI for Complementary Trees** | Requests AI-suggested follow-up questionnaires based on answers |
| **Back to Questions** | Return to continue answering (opens Review Modal) |
| **Submit & Generate Profile** | Finalizes and saves the profile output |

#### AI Suggestions Panel

| Element | Description |
|---------|-------------|
| **Suggestions List** | AI-generated tree recommendations with Save buttons |
| **Suggestion Preview** | Shows JSON structure of selected AI suggestion |

---

## Review & Edit Modal

Accessible via "Back to Questions" on finish screen.

### Features

| Element | Description |
|---------|-------------|
| **Answered Questions List** | Numbered list of all answered questions with editable inputs |
| **User Selection** | Change/add answering user for the session |
| **New Questions Panel** | If edits trigger new branches, questions appear here |
| **Apply Changes** | Recomputes branches based on edited answers |
| **Cancel** | Close modal without changes |
| **Submit** | Submit directly from modal |

---

# Section 2: Use Cases & Testing

## Use Case 1: Running a Simple Linear Questionnaire

**Objective**: Test basic questionnaire flow with sequential questions.

### Test Tree JSON

Save this as `simple_test.json` in `decision_tree/trees/`:

```json
{
  "start": "q_name",
  "nodes": {
    "q_name": {
      "id": "q_name",
      "type": "text",
      "prompt": "What is your name?",
      "next": "q_role"
    },
    "q_role": {
      "id": "q_role",
      "type": "single_select",
      "prompt": "What is your role?",
      "options": ["Developer", "Designer", "Manager", "QA"],
      "next": "q_experience"
    },
    "q_experience": {
      "id": "q_experience",
      "type": "yes_no",
      "prompt": "Do you have more than 3 years of experience?",
      "next": "end"
    },
    "end": {
      "id": "end",
      "type": "end",
      "prompt": "Thank you for completing the questionnaire!"
    }
  }
}
```

### Steps to Test

1. Navigate to `/questionnarie_decision_tree`
2. Paste the sample json in the debug/test section
3. Click **Start**
4. Add a user: `Test User, Tester` → click **Add**
5. Select the user from dropdown
6. Answer the name question → click **Next**
7. Select a role → click **Next**
8. Choose Yes or No → click **Next**
9. Review the answers JSON on finish screen
10. Click **Submit & Generate Profile**

### Expected Results

- Progress bar advances with each answer
- All three question types render correctly
- Finish screen shows complete answers object

---

## Use Case 2: Testing Branching Logic

**Objective**: Verify conditional branching works correctly.

### Test Tree JSON

Save this as `branch_test.json`:

```json
{
  "start": "q_category",
  "nodes": {
    "q_category": {
      "id": "q_category",
      "type": "single_select",
      "prompt": "Select your department:",
      "options": ["Engineering", "Marketing", "Sales"],
      "next": "branch_dept"
    },
    "branch_dept": {
      "id": "branch_dept",
      "type": "branch",
      "next": [
        { "when": { "equals": "Engineering" }, "goto": "q_tech_stack" },
        { "when": { "equals": "Marketing" }, "goto": "q_campaigns" },
        { "default": true, "goto": "q_general" }
      ],
      "use_answer_from": "q_category"
    },
    "q_tech_stack": {
      "id": "q_tech_stack",
      "type": "multi_select",
      "prompt": "Which technologies do you work with?",
      "options": ["Python", "JavaScript", "Java", "Go"],
      "next": "end"
    },
    "q_campaigns": {
      "id": "q_campaigns",
      "type": "text",
      "prompt": "Describe your current marketing campaign:",
      "next": "end"
    },
    "q_general": {
      "id": "q_general",
      "type": "text",
      "prompt": "What are your main responsibilities?",
      "next": "end"
    },
    "end": {
      "id": "end",
      "type": "end",
      "prompt": "Profile complete!"
    }
  }
}
```

### Steps to Test

1. Load `branch_test.json` and start
2. **Test Path A**: Select "Engineering" → verify `q_tech_stack` appears
3. Restart and **Test Path B**: Select "Marketing" → verify `q_campaigns` appears
4. Restart and **Test Path C**: Select "Sales" → verify `q_general` appears

### Expected Results

- Branch node is invisible (no prompt shown)
- Correct follow-up question based on selection
- Each path reaches the end node

---

## Use Case 3: Testing For-Each Loops

**Objective**: Verify iteration over list items.

### Test Tree JSON

Save this as `loop_test.json`:

```json
{
  "start": "q_team_members",
  "nodes": {
    "q_team_members": {
      "id": "q_team_members",
      "type": "list",
      "prompt": "List your team members (comma-separated):",
      "next": "loop_members"
    },
    "loop_members": {
      "id": "loop_members",
      "type": "for_each",
      "source": "q_team_members",
      "item_var": "member",
      "next": "q_member_skill",
      "after": "end"
    },
    "q_member_skill": {
      "id": "q_member_skill",
      "type": "text",
      "prompt": "What is {{answers.__loop_members.current}}'s primary skill?",
      "next": "loop_members"
    },
    "end": {
      "id": "end",
      "type": "end",
      "prompt": "Team profile complete!"
    }
  }
}
```

### Steps to Test

1. Load `loop_test.json` and start
2. Enter: `Alice, Bob, Charlie` → click **Next**
3. Verify question shows "What is Alice's primary skill?"
4. Answer and continue for each member
5. After Charlie, verify it reaches the end node

### Expected Results

- Loop iterates exactly 3 times (one per team member)
- Template `{{answers.__loop_members.current}}` renders correctly
- After last item, flow continues to `after` node

---

## Use Case 4: Testing Back Navigation & Edit

**Objective**: Verify session rewind and answer editing.

### Steps to Test

1. Start any questionnaire and answer 3-4 questions
2. Click **← Back** button
3. Verify previous question reappears with saved answer
4. Change the answer → click **Next**
5. Continue to finish screen
6. Click **Back to Questions** to open Review Modal
7. Edit an answer in the modal → click **Apply Changes**
8. Verify if branching changed, new questions appear

### Expected Results

- Back button restores previous state
- Edited answers persist through navigation
- Branch recalculation works when answers change

---

## Use Case 5: Testing CSV Upload & Conversion

**Objective**: Verify CSV to JSON conversion.

### Test CSV Content

Create a file `test_upload.csv`:

```csv
id,type,prompt,next,options
welcome,text,What is your project name?,goal,
goal,single_select,What is your main goal?,end,"[""Launch MVP"",""Improve Performance"",""Add Features""]"
end,end,Thank you!,,
```

### Steps to Test

1. Navigate to `/questionnarie_decision_tree`
2. In CSV Upload section, click **Browse** and select the CSV
3. Enter filename: `uploaded_test.json`
4. Optionally set Start Node: `welcome`
5. Click **Convert & Save**
6. Verify JSON appears in preview
7. Click **Select Uploaded Tree** → **Start**
8. Complete the questionnaire

### Expected Results

- CSV parses without errors
- JSON structure appears in preview
- Tree becomes available in dropdown
- Questionnaire runs correctly

---

## Use Case 6: Testing Debug/Auto-Run Mode

**Objective**: Verify automatic answer filling for testing.

### Steps to Test

1. Load any tree (e.g., `simple_test.json`)
2. In Debug Answers textarea, paste:
```json
{
  "q_name": "Test User",
  "q_role": "Developer",
  "q_experience": true
}
```
3. Set Answering user: `debug`
4. Click **Start (auto-run to finish if answers available)**
5. Verify it jumps directly to finish screen

### Expected Results

- All matching answers auto-filled
- If an answer is missing, questionnaire stops at that question
- Finish screen shows all auto-filled answers

---

## Use Case 7: Complete Decision Tree Example

**Objective**: Test a comprehensive tree with all features.

### Test Tree JSON

Save this as `comprehensive_test.json`:

```json
{
  "start": "q_event_type",
  "nodes": {
    "q_event_type": {
      "id": "q_event_type",
      "type": "single_select",
      "prompt": "What type of event are you planning?",
      "options": ["Conference", "Workshop", "Team Building"],
      "next": "branch_event"
    },
    "branch_event": {
      "id": "branch_event",
      "type": "branch",
      "next": [
        { "when": { "equals": "Conference" }, "goto": "q_conf_size" },
        { "when": { "equals": "Workshop" }, "goto": "q_workshop_topic" },
        { "default": true, "goto": "q_team_activities" }
      ],
      "use_answer_from": "q_event_type"
    },
    "q_conf_size": {
      "id": "q_conf_size",
      "type": "single_select",
      "prompt": "Expected number of attendees?",
      "options": ["< 50", "50-100", "100-500", "> 500"],
      "next": "q_speakers_list"
    },
    "q_speakers_list": {
      "id": "q_speakers_list",
      "type": "list",
      "prompt": "List your confirmed speakers (comma-separated):",
      "next": "loop_speakers"
    },
    "loop_speakers": {
      "id": "loop_speakers",
      "type": "for_each",
      "source": "q_speakers_list",
      "item_var": "speaker",
      "next": "q_speaker_topic",
      "after": "q_venue"
    },
    "q_speaker_topic": {
      "id": "q_speaker_topic",
      "type": "text",
      "prompt": "What topic will {{answers.__loop_speakers.current}} present?",
      "next": "loop_speakers"
    },
    "q_workshop_topic": {
      "id": "q_workshop_topic",
      "type": "text",
      "prompt": "What is the workshop topic?",
      "next": "q_hands_on"
    },
    "q_hands_on": {
      "id": "q_hands_on",
      "type": "yes_no",
      "prompt": "Will this be a hands-on workshop?",
      "next": "q_venue"
    },
    "q_team_activities": {
      "id": "q_team_activities",
      "type": "multi_select",
      "prompt": "Select planned activities:",
      "options": ["Escape Room", "Cooking Class", "Sports", "Volunteer Work", "Trivia Night"],
      "next": "q_venue"
    },
    "q_venue": {
      "id": "q_venue",
      "type": "yes_no",
      "prompt": "Have you secured a venue?",
      "next": "q_notes"
    },
    "q_notes": {
      "id": "q_notes",
      "type": "text",
      "prompt": "Any additional notes or requirements?",
      "next": "end"
    },
    "end": {
      "id": "end",
      "type": "end",
      "prompt": "Event planning profile complete! Review your answers below."
    }
  }
}
```

### Test Scenarios

| Scenario | Path | Expected Questions |
|----------|------|-------------------|
| **A** | Conference | event_type → conf_size → speakers_list → [loop] → venue → notes |
| **B** | Workshop | event_type → workshop_topic → hands_on → venue → notes |
| **C** | Team Building | event_type → team_activities → venue → notes |

### Steps to Test

1. Load `comprehensive_test.json`
2. Test each scenario path
3. For Conference path, enter 2-3 speakers to test the loop
4. Verify template rendering in loop questions
5. Complete to finish and verify all answers captured

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **"Select a user" error** | Add a user in format `Name, Role` before answering |
| **Tree not appearing** | Check if JSON file is valid and saved in `decision_tree/trees/` |
| **Branch not working** | Verify `use_answer_from` points to correct node ID |
| **Loop stuck** | Ensure loop's `next` points back to the for_each node |
| **Template not rendering** | Check syntax: `{{answers.node_id}}` or `{{answers.__loop_id.current}}` |
| **CSV conversion fails** | Verify CSV has all required columns and valid JSON in options |

### API Endpoints Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/questionnarie_decision_tree` | GET | Load the runner UI |
| `/trees` | GET | List available tree files |
| `/get_tree?name=<filename>` | GET | Fetch a specific tree JSON |
| `/dt/start` | POST | Start a new session |
| `/dt/answer` | POST | Submit an answer |
| `/dt/rewind` | POST | Reset session and replay answers |
| `/dt/users` | GET/POST | Manage answering users |
| `/dt/profile/<sid>` | GET | Get current profile for session |
| `/trees/upload_csv` | POST | Upload and convert CSV |
| `/trees/<name>` | DELETE | Delete a tree file |

---

## Related Documentation

- **[Decision Tree Editor Guide](EDITOR_README.md)** - Create and edit decision trees visually
- **Tree Files Location**: `decision_tree/trees/`
- **Engine Source**: `decision_tree/question_nodes_interpreter.py`
