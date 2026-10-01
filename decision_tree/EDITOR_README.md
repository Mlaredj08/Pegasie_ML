# Decision Tree Editor - Complete User Guide

## Overview

The **Decision Tree Editor** is a visual, drag-and-drop tool for creating interactive questionnaires and decision trees. It generates JSON files compatible with the JFIP Decision Tree Engine, allowing you to build complex, branching questionnaires with parametrized questions, conditional logic, and user profile effects.

## Accessing the Editor

1. **Login** to the JFIP web application
2. Navigate to the **Dashboard** (main menu)
3. In the **Experimental Zone** section, click **"Create or Edit Decision Tree"**
4. The visual editor opens at `/tree_editor`

## Interface Layout

The editor consists of:
- **Left Sidebar**: File operations, node properties, and configuration panels
- **Right Canvas**: Visual flow diagram with draggable nodes and connections
- **Toolbar**: Zoom, auto-layout, and view controls

---

## Node Types & Configurations

### 1. **Text Question** (`text`)
Collects free-form text input from users.

**Properties:**
- **ID**: Unique identifier (e.g., `user_name`)
- **Prompt**: Question text (supports templates)
- **Next**: Direct link to next node
- **Effects**: Actions to perform with the answer

**Example:**
```
ID: user_name
Prompt: What is your full name?
```

### 2. **Yes/No Question** (`yes_no`)
Binary choice question returning `true`/`false`.

**Properties:**
- **ID**: Unique identifier
- **Prompt**: Question text
- **Next**: Direct link to next node
- **Effects**: Actions based on the answer

**Example:**
```
ID: has_experience
Prompt: Do you have prior experience in this field?
```

### 3. **List Question** (`list`)
Allows users to input multiple items, one per line.

**Properties:**
- **ID**: Unique identifier
- **Prompt**: Instructions for the list
- **Next**: Direct link to next node
- **Effects**: Actions with the list of items

**Example:**
```
ID: favorite_movies
Prompt: List your top 5 favorite movies (one per line):
```

### 4. **Single Select** (`single_select`)
Multiple choice question allowing only one selection.

**Properties:**
- **ID**: Unique identifier
- **Prompt**: Question text
- **Options**: Predefined choices OR
- **Options from answer of**: Pull options from another node's answer
- **Split**: Delimiter for splitting source answer into options
- **Next**: Direct link to next node
- **Effects**: Actions with selected option

**Example:**
```
ID: preferred_language
Prompt: What is your preferred programming language?
Options: Python, JavaScript, Java, C#, Go
```

### 5. **Multi Select** (`multi_select`)
Multiple choice question allowing multiple selections.

**Properties:**
- **ID**: Unique identifier
- **Prompt**: Question text
- **Options**: Predefined choices OR
- **Options from answer of**: Pull options from another node's answer
- **Split**: Delimiter for splitting source answer into options
- **Next**: Direct link to next node
- **Effects**: Actions with selected options array

**Example:**
```
ID: programming_skills
Prompt: Which programming languages do you know? (Select all that apply)
Options: Python, JavaScript, Java, C#, Go, Rust, Swift
```

### 6. **Branch Node** (`branch`)
Conditional routing based on previous answers.

**Properties:**
- **ID**: Unique identifier
- **Use answer from**: Which node's answer to evaluate (defaults to previous)
- **Branch Rules**: Array of conditions with destinations

**Branch Rule Types:**
- **equals**: Exact match (`answer == value`)
- **in**: Answer is in array (`answer in [values]`)
- **contains_any**: Answer contains any of the values
- **contains_all**: Answer contains all values  
- **is_true**: Answer is truthy
- **is_false**: Answer is falsy
- **non_empty**: Answer is not empty
- **default**: Fallback rule (always place last)

**Example:**
```
ID: experience_branch
Use answer from: has_experience
Rules:
  - When: equals "true" → Goto: advanced_questions  
  - When: default → Goto: beginner_questions
```

### 7. **For Each Loop** (`for_each`)
Iterates through a list, running a sub-flow for each item.

**Properties:**
- **ID**: Unique identifier
- **Source**: Node ID whose answer provides the list
- **Item variable**: Variable name for current item (e.g., `movie`)
- **Next**: First node in the loop body
- **After**: Node to go to when loop completes

**Example:**
```
ID: movie_rating_loop
Source: favorite_movies
Item variable: current_movie
Next: rate_movie_question
After: final_summary
```

**In the loop body:**
- Use `{{answers.__for_each_id.current}}` to reference current item
- Use `{{answers.movie_rating_loop.current}}` for the current movie

### 8. **End Node** (`end`)
Terminates the questionnaire flow.

**Properties:**
- **ID**: Unique identifier
- **Prompt**: Final message/summary
- **Effects**: Final actions (e.g., save profile data)

**Example:**
```
ID: thank_you
Prompt: Thank you for completing the questionnaire!
```

---

## Parametrized Questions (Templates)

Use template syntax in **any prompt** to insert previous answers:

### Basic Template Syntax
- **`{{answers.node_id}}`** - Insert answer from specific node
- **`{{answers.node_id|csv}}`** - Format list answers as comma-separated values
- **`{{answer}}`** - Insert previous node's answer (rarely used)

### Examples

**Text Personalization:**
```
Node: welcome_message
Prompt: Hello {{answers.user_name}}, welcome to our assessment!
```

**List References:**
```
Node: movie_discussion  
Prompt: You mentioned these movies: {{answers.favorite_movies}}. Let's discuss each one.
```

**Conditional Text:**
```
Node: experience_followup
Prompt: Since you {{answers.has_experience}} experience, we'll tailor the questions accordingly.
```

**For Each Current Item:**
```
Node: rate_movie (inside for_each loop)
Prompt: How would you rate "{{answers.movie_rating_loop.current}}" on a scale of 1-10?
```

---

## Visual Canvas Operations

### Adding Nodes
1. Click any **Add Node** button in the sidebar (Text, Yes/No, List, etc.)
2. Node appears on canvas at center with random offset
3. Click the node to select and configure it

### Connecting Nodes
**Method 1: Drag Connection**
1. Click and drag from a node's **output port** (bottom blue dot)
2. Drop on target node's **input port** (top blue dot)
3. Connection line appears with arrowhead

**Method 2: Properties Panel**
1. Select source node
2. Use **"Next"** dropdown to choose destination
3. Connection updates automatically

### Moving Nodes
- **Click and drag** any node to reposition
- Canvas supports **pan** (drag empty space) and **zoom** (mouse wheel)

### Deleting Nodes
- **Hover** over a node and click the **red X** button
- Or select node and click **Delete** button in properties panel
- All references to deleted node are automatically cleaned up

### Auto Layout
- Click **Auto Layout** button (grid icon) to automatically arrange nodes
- Uses topological sorting for clean flow visualization

### Zoom & Pan Controls
- **Zoom In/Out**: Toolbar buttons or mouse wheel
- **Reset Zoom**: Aspect ratio button
- **Fit to View**: Adjusts zoom/pan to show all nodes
- **Pan**: Drag empty canvas areas

---

## Effects System

Effects modify the user's profile during the questionnaire. They execute when a node's answer is submitted.

### Effect Operations

**1. Set (`set`)**
- Overwrites a profile field with new value
- `path`: Profile field path (e.g., `skills.primary`)  
- `value`: Fixed value OR `from_answer: true` to use node's answer

**2. Append (`append`)**  
- Adds item to end of array
- Creates array if field doesn't exist

**3. Extend Set (`extend_set`)**
- Merges list items into existing array
- Removes duplicates automatically

**4. Merge Map (`merge_map`)**
- Merges object properties into existing object
- Creates object if field doesn't exist

### Effect Examples

**Basic Set:**
```
Operation: set
Path: user.name  
From Answer: ✓
```

**Append to List:**
```
Operation: append
Path: user.skills
Value: {{answers.new_skill}}
```

**Fixed Value Set:**
```
Operation: set  
Path: user.status
Value: "completed_assessment"
```

**Merge Object:**
```
Operation: merge_map
Path: user.preferences
Value: {"theme": "dark", "language": "en"}
```

---

## File Operations

### Loading Existing Trees
1. **Tree File** dropdown shows available JSON files
2. Click **Load** button (download icon) to open selected tree
3. Canvas populates with nodes and connections
4. "New tree" option starts fresh

### Saving Trees
1. Enter filename in **save field** (auto-adds `.json`)
2. Click **Save** button  
3. Tree JSON is generated and saved to `decision_tree/trees/`
4. File becomes available in tree selection dropdown

### Setting Start Node
1. Enter node ID in **"Start node ID"** field
2. Click **Set** button (play icon)
3. Start node gets green "START" badge
4. This determines questionnaire entry point

### JSON Preview
- Click **"Preview JSON"** to see generated structure
- Modal shows formatted JSON output
- **Copy** button copies to clipboard
- JSON is compatible with Decision Tree Engine

---

## Advanced Features

### Dynamic Options
Instead of static option lists, pull options from previous answers:

**Setup:**
1. Create source node (text/list) with ID `categories`
2. Create select node with:
   - **Options from answer of**: `categories`
   - **Split**: `,` (if source is comma-separated text)

**Use Case:**
```
Node 1 (text): "Enter job categories (comma-separated)"
Answer: "Developer, Designer, Manager"

Node 2 (single_select): Options automatically become ["Developer", "Designer", "Manager"]
```

### Complex Branching

**Multiple Conditions:**
```
Branch Rules:
1. When: equals "senior" → Goto: senior_track
2. When: in ["junior","mid"] → Goto: standard_track  
3. When: non_empty → Goto: general_questions
4. Default → Goto: error_node
```

**Array Conditions:**
```
For multi_select answers:
1. When: contains_any ["python","java"] → Goto: backend_questions
2. When: contains_all ["html","css","js"] → Goto: frontend_questions
3. Default → Goto: general_programming
```

### For Each Patterns

**Rating Each Item:**
```
Flow: movies_list → movie_loop → rate_movie → (back to loop) → summary

movie_loop (for_each):
- Source: movies_list
- Item variable: current_movie  
- Next: rate_movie
- After: summary

rate_movie (text):
- Prompt: "Rate {{answers.movie_loop.current}} (1-10):"
- Next: movie_loop (continues loop)
```

**Building Collections:**
```
Each iteration can append to arrays:
Effect: append
Path: ratings
From Answer: true
```

---

## Complete Example Workflow

### Scenario: Programming Skills Assessment

**1. Create Entry Point**
```
Node: welcome (text)
Prompt: What is your name?
Next: experience_check
```

**2. Add Branch Logic**
```  
Node: experience_check (yes_no)
Prompt: Do you have programming experience?
Next: experience_branch

Node: experience_branch (branch)
Use answer from: experience_check
Rules:
  - equals "true" → experienced_path
  - default → beginner_path
```

**3. Experienced Path**
```
Node: experienced_path (multi_select)
Prompt: Which languages do you know, {{answers.welcome}}?
Options: Python, JavaScript, Java, C#, Go
Next: skill_level
```

**4. For Each Skills Assessment**
```
Node: skill_assessment_loop (for_each)
Source: experienced_path
Item variable: language
Next: rate_language_skill
After: final_summary

Node: rate_language_skill (single_select)  
Prompt: Rate your {{answers.skill_assessment_loop.current}} skills:
Options: Beginner, Intermediate, Advanced, Expert
Effects:
  - append to path: skills_ratings
```

**5. Final Summary**
```
Node: final_summary (end)
Prompt: Thanks {{answers.welcome}}! Assessment complete.
Effects:
  - set path: assessment.completed value: true
```

---

## Best Practices

### Node Naming
- Use **descriptive IDs**: `user_name` not `q1`
- Follow **snake_case** convention
- Include **node type**: `skills_select`, `experience_branch`

### Prompt Writing  
- Be **specific and clear**
- Use **templates** for personalization
- Include **instructions** for complex questions
- Test **different user paths**

### Flow Design
- Start with **simple linear** flows
- Add **branches** for major decision points  
- Use **for_each** for repetitive patterns
- Always include **end nodes**

### Testing
- Use **Preview JSON** to verify structure
- Load tree in **Decision Tree Runner** (`/questionnarie_decision_tree`)
- Test **all branching paths**
- Verify **template rendering**

---

## Troubleshooting

### Common Issues

**"Node ID already exists"**
- Solution: Use unique IDs for each node
- Check existing nodes before renaming

**"Invalid JSON in branch rules"**
- Solution: Ensure proper rule syntax
- Use dropdown conditions, not manual JSON

**"Template not rendering"**
- Solution: Verify referenced node exists
- Check template syntax: `{{answers.node_id}}`
- Ensure source node appears before template usage

**"Connection not working"**
- Solution: Verify target node exists
- Check branch rules point to valid nodes
- Use connection dots, not manual typing

**"Save failed"**
- Solution: Enter valid filename
- Check write permissions to trees folder
- Verify JSON structure in preview

### Browser Requirements
- Modern browser with **JavaScript enabled**
- **Canvas/SVG support** for visual editor
- **Local storage** for temporary state

### Performance Notes
- Editor handles **100+ nodes** efficiently
- Complex templates may slow rendering
- Auto-layout works best with **<50 nodes**

---

## JSON Structure Reference

Generated JSON follows this format:

```json
{
  "start": "entry_node_id",
  "nodes": {
    "node_id": {
      "id": "node_id",
      "type": "text|yes_no|list|single_select|multi_select|branch|for_each|end",
      "prompt": "Question text with {{templates}}",
      "next": "next_node_id" | [branch_rules],
      "options": ["option1", "option2"],
      "options_from_answer_of": "source_node_id",
      "split": ",",
      "use_answer_from": "source_node_id", 
      "effects": [effect_objects],
      "source": "list_node_id",
      "item_var": "variable_name",
      "after": "after_loop_node_id"
    }
  }
}
```

This JSON is **fully compatible** with:
- Decision Tree Engine (`question_nodes_interpreter.py`)
- Decision Tree Runner (`/questionnarie_decision_tree`)  
- Existing tree files in `trees/` folder

---

## Support & Development

- **Location**: `/tree_editor` route in JFIP web app
- **Files**: `templates/tree_editor.html`, `static/js/tree_editor.js`
- **Backend**: Reuses existing `/trees`, `/get_tree`, `/dt/save_suggested_tree` endpoints
- **Storage**: Trees saved to `decision_tree/trees/` as JSON files

For issues or feature requests, consult the development team or check the application logs.
