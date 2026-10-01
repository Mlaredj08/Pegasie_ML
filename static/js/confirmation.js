let results = {};
let q_issue_count = 0;

function reopenCard(cardId) {
    const card = document.getElementById(cardId);
    const body = card.querySelector(".card-body");
    body.style.display = "block";
    card.classList.remove("collapsed");
    card.style.opacity = "1";
}

function toggleGroup(groupId) {
    const groupDiv = document.getElementById(groupId);
    groupDiv.style.display = groupDiv.style.display === "none" ? "block" : "none";
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatNumberOrDash(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}


function renderQuestions(data) {
    const fieldValues = data?.__meta?.field_values || [];
    const getFieldOptions = (fname) =>
        (fieldValues.find(f => f.field_name === fname)?.list_of_values) || [];
    const container = document.getElementById("questions-container");
    container.innerHTML = "";
    let qIndex = 0;

    // Helpers
    const toFlat = (x) => Array.isArray(x) ? x.flat(Infinity) : [];
    const toAvg = (arr) => {
        const nums = toFlat(arr).filter(n => typeof n === "number" && !isNaN(n));
        if (!nums.length) return null;
        const sum = nums.reduce((a, b) => a + b, 0);
        return (sum / nums.length);
    };

    // Collect orphaned predictions here
    const orphaned = [];

    // Group non-orphaned by field_name
    const grouped = {};
    for (const [predictedValue, questions] of Object.entries(data)) {
      if (!Array.isArray(questions)) continue;

      for (const q of questions) {
        const isOrphaned =
          String(q.question || "").trim().toUpperCase().startsWith("ORPHANED") ||
          q.is_orphan === true;

        const item = { ...q, predictedValue };

        if (isOrphaned) {
          const conf = toAvg(q.confidence);
          const kws  = Array.isArray(q.keywords) ? q.keywords : [];
          const issuesArr = Array.isArray(q.list_of_issues)
            ? (Array.isArray(q.list_of_issues[0]) ? q.list_of_issues[0] : q.list_of_issues)
            : [];

          if (issuesArr.length === 0) {
            // fallback in case structure is unexpected
            orphaned.push({
              predictedValue,
              targetedField: q.field_name,
              confiedence: conf,
              keywords: kws,
              issue: "—",
              orphan_reason: q.orphan_reason ?? null
            });
          } else {
            for (const issue of issuesArr) {
              orphaned.push({
                predictedValue,
                targetedField: q.field_name,
                confiedence: conf,             // keep original label
                keywords: kws,
                issue: issue || "—",
                orphan_reason: q.orphan_reason ?? null
              });
            }
          }
          continue; // skip normal cards
        }

        const fieldName = q.field_name;
        if (!grouped[fieldName]) grouped[fieldName] = [];
        grouped[fieldName].push(item);
      }
    }

    // Use server-recommended order if present, otherwise natural order
    const fieldOrder = (data?.__meta?.field_order && Array.isArray(data.__meta.field_order))
      ? data.__meta.field_order
      : Object.keys(grouped);

    // Also capture stats for header badges
    const stats = data?.__meta?.field_stats || {};

    // Render normal grouped cards (non-orphaned only)
    for (const fieldName of fieldOrder) {
          const fieldQuestions = grouped[fieldName] || [];
          if (!fieldQuestions.length) continue;
          // ... (rest of existing rendering block stays the same)

        const groupId = `group-${fieldName}`;

        // Group header
        const groupHeader = document.createElement("div");
        groupHeader.className = "card mb-3 border-info";
        groupHeader.style.cursor = "pointer";
        groupHeader.addEventListener("click", () => toggleGroup(groupId));
        var totalIssuesPerField = 0;
        var badgeText = "$$badgeText"
        var htmlStr = `<div class="card-header mb-2">`
        htmlStr += `<strong>${fieldName}</strong>`;
        htmlStr += `<span class="badge bg-info ms-2">${badgeText}</span>`;
        htmlStr += `</div>`
         groupHeader.innerHTML = htmlStr;

        const groupDiv = document.createElement("div");
        groupDiv.id = groupId;

        // Process each question card
        fieldQuestions.forEach((q, index) => {
            totalIssuesPerField += q.cluster_issues_count;
            const cardId = `question-${qIndex}`;
            const listId = `issues-list-${qIndex}`;
            const keywordsId = `keywords-box-${qIndex}`;
            const keywordsInputId = `keywords-input-${qIndex}`;
            const originalKeywords = `keywords-raw-${qIndex}`;
            const card = document.createElement("div");
            const safePredictedValue = (q.predictedValue || "").replace(/'/g, "\\'");
            const question_format = formatQuestionText(q.question, originalKeywords);
            const optionsForField = getFieldOptions(fieldName);
            const predictedSelectId = `predicted-select-${qIndex}`;
            const predictedBoxId = `predicted-box-${qIndex}`;

            card.className = "card mb-3";
            card.id = cardId;

            card.innerHTML = `
              <div class="card-header">
                  <div>${question_format}</div>
                  <button class="reopen-btn">Reopen</button>
              </div>
              <div class="card-body">
                  <div class="mb-2">
                      Confirm this prediction?
                      <span class="fs-5 ms-3">#Issues: ${q.cluster_issues_count}</span>
                  </div>
                  <div class="d-flex align-items-center mb-2 justify-content-between">
                      <div>
                          <button class="btn btn-success me-2">Yes</button>
                          <button class="btn btn-danger me-2">No</button>
                          <button class="btn btn-warning btn-sm">Edit</button>
                      </div>
                      <button class="btn btn-sm btn-secondary">+</button>
                  </div>

                  <div id="${predictedBoxId}" style="display:none;" class="mb-2">
                      <label for="${predictedSelectId}" class="form-label">Edit ${escapeHtml(fieldName)} value:</label>
                      ${
                        optionsForField.length
                          ? `<select id="${predictedSelectId}" class="form-select form-select-sm">
                                ${optionsForField.map(v => `
                                  <option value="${escapeHtml(v)}" ${v === q.predictedValue ? 'selected' : ''}>${escapeHtml(v)}</option>
                                `).join('')}
                             </select>`
                          : `<input type="text" id="${predictedSelectId}" class="form-control form-control-sm" value="${escapeHtml(q.predictedValue)}">`
                      }
                  </div>
              </div>


            `;
//            card.innerHTML = `
//              <div class="card-header">
//                  <div>${question_format}</div>
//                  <button class="reopen-btn">Reopen</button>
//              </div>
//              <div class="card-body">
//                  <div class="mb-2">
//                      Confirm this prediction?
//                      <span class="fs-5 ms-3">#Issues: ${q.cluster_issues_count}</span>
//                  </div>
//                  <div class="d-flex align-items-center mb-2 justify-content-between">
//                      <div>
//                          <button class="btn btn-success me-2">Yes</button>
//                          <button class="btn btn-danger me-2">No</button>
//                          <button class="btn btn-warning btn-sm">Edit</button>
//                      </div>
//                      <button class="btn btn-sm btn-secondary">+</button>
//                  </div>
//
//                  <div id="${predictedBoxId}" style="display:none;" class="mb-2">
//                      <label for="${predictedSelectId}" class="form-label">Edit ${escapeHtml(fieldName)} value:</label>
//                      ${
//                        optionsForField.length
//                          ? `<select id="${predictedSelectId}" class="form-select form-select-sm">
//                                ${optionsForField.map(v => `
//                                  <option value="${escapeHtml(v)}" ${v === q.predictedValue ? 'selected' : ''}>${escapeHtml(v)}</option>
//                                `).join('')}
//                             </select>`
//                          : `<input type="text" id="${predictedSelectId}" class="form-control form-control-sm" value="${escapeHtml(q.predictedValue)}">`
//                      }
//                  </div>
//
//                  <!-- existing keywords editor (still useful) -->¿\
//                  <div id="${keywordsId}" style="display: none;" class="mb-2">
//                      <label for="${keywordsInputId}" class="form-label">Edit Keywords:</label>
//                      <input type="text" id="${keywordsInputId}" class="form-control form-control-sm" value="${(q.keywords || []).join(', ')}">
//                  </div>
//              </div>
//            `;
            // Build the list of issues
            const listEl = document.createElement("ul");
            listEl.id = listId;
            listEl.style.display = "none";
            listEl.style.paddingLeft = "1.5rem";
            listEl.style.marginBottom = "0";
            listEl.style.listStyleType = "disc";

            const issues = Array.isArray(q.list_of_issues) ? (q.list_of_issues[0] || []) : [];
            issues.forEach(issue => {
                const li = document.createElement("li");
                li.textContent = issue;
                listEl.appendChild(li);
            });

            const cardBody = card.querySelector(".card-body");
            cardBody.appendChild(listEl);

            // Append the card to the group
            groupDiv.appendChild(card);


            // Build footer with cohesion, density and keywords (horizontal)
            const footer = document.createElement("div");
            footer.className = "card-footer meta-footer bg-light";
            const coh = formatNumberOrDash(q.similarity_cohesion, 3);
            const den = formatNumberOrDash(q.similarity_density, 3);
            const cent = q.cluster_centroid;
            const kws = Array.isArray(q.keywords) ? q.keywords.join(", ") : "";
            footer.innerHTML = `
              <div class="d-flex align-items-center gap-3 flex-wrap">
                <div class="meta-item"><strong>Cohesion:</strong> ${coh}</div>
                <div class="meta-item"><strong>Density:</strong> ${den}</div>
                <div class="meta-item"><strong>Centroid:</strong> ${cent}</div>
                <div class="meta-keywords"><strong>Tokens:</strong> ${escapeHtml(kws) || "—"}</div>
              </div>
            `;
            card.appendChild(footer);

// Event handlers (no inline HTML)
            card.querySelector(".card-header").addEventListener("click", () => reopenCard(cardId));

            // Yes button
            card.querySelector(".btn-success").addEventListener("click", (event) => {
              event.stopPropagation();
              collapseCardYes(
                cardId,
                fieldName,
                q.predictedValue,         // original prediction
                index,
                q.list_of_issues,
                q.keywords,
                keywordsInputId,
                originalKeywords,
                predictedSelectId         // NEW
              );
            });

            // No button
            card.querySelector(".btn-danger").addEventListener("click", (event) => {
              event.stopPropagation();
              collapseCard(
                cardId,
                fieldName,
                q.predictedValue,         // original prediction
                index,
                q.list_of_issues,
                q.keywords,
                keywordsInputId,
                originalKeywords,
                predictedSelectId         // NEW
              );
            });

            // Edit button: toggle BOTH the predicted-value box and the keywords box
            card.querySelector(".btn-warning").addEventListener("click", (event) => {
              event.stopPropagation();
              const box1 = document.getElementById(predictedBoxId);
              const box2 = document.getElementById(keywordsId);
              if (box1) box1.style.display = (box1.style.display === "none" ? "block" : "none");
              if (box2) box2.style.display = (box2.style.display === "none" ? "block" : "none");
            });

            // Toggle issues list button
            card.querySelector(".btn-secondary").addEventListener("click", (event) => {
                event.stopPropagation();
                toggleIssues(listId);
            });

            qIndex++;
        });

        // Update badge text
        groupHeader.innerHTML = groupHeader.innerHTML.replace(badgeText, totalIssuesPerField);

        // Add group header and content
        container.appendChild(groupHeader);
        container.appendChild(groupDiv);
    }

    // Append orphaned summary box at the end (informational only)
    if (orphaned.length) {
        const summaryCard = document.createElement("div");
        summaryCard.className = "card mb-3 border-info";
        summaryCard.innerHTML = `
            <div class="card-header bg-info-subtle">
                <strong>Orphaned Predictions Summary</strong>
                <span class="badge bg-info ms-2">${orphaned.length}</span>
            </div>
            <div class="card-body">
                <p class="text-muted mb-3">
                    These clusters were detected as <em>ORPHANED</em> and are presented here for your awareness. 
                    They do not require action and have no confirmation buttons.
                </p>
                <div class="table-responsive">
                    <table class="table table-sm align-middle">
                    <thead>
                        <tr>
                            <th>Predicted Value</th>
                            <th>Targeted field</th>
                            <th>confiedence</th>
                            <th>keywords</th>
                            <th>issue</th>   <!-- NEW COLUMN -->
                        </tr>
                    </thead>
                    <tbody>
                        ${orphaned.map(item => `
                            <tr>
                                <td>${item.predictedValue}</td>
                                <td>${item.targetedField}</td>
                                <td>${item.confiedence == null ? "—" : item.confiedence.toFixed(2)}</td>
                                <td>${item.keywords.length ? item.keywords.join(", ") : "—"}</td>
                                <td>${item.issue}</td>  <!-- NEW CELL -->
                            </tr>
                        `).join("")}
                    </tbody>
                    </table>
                </div>
            </div>
        `;
        summaryCard.querySelector(".card-body").classList.add("d-none");
        summaryCard.querySelector(".card-header").setAttribute("aria-expanded", "false");
        container.appendChild(summaryCard);

        const header = summaryCard.querySelector(".card-header");
        const body   = summaryCard.querySelector(".card-body");
        header.style.cursor = "pointer";
        header.setAttribute("aria-expanded", "true");
        
        header.addEventListener("click", () => {
            body.classList.toggle("d-none");
        
            const expanded = header.getAttribute("aria-expanded") === "true";
            header.setAttribute("aria-expanded", (!expanded).toString());
        });
        
    }
}


function formatQuestionText(inputText, cardKeywordsId) {
    const container = document.createElement("div");
    var isCentroid = false;
    var parts = inputText.split(/(?=\b(?:Target Field|Value|Keywords representing the group):)/);
    var questionType = "Keywords representing the group"
    if (inputText.includes("—: ")){
        parts = inputText.split(/(?=\b(?:Target Field|Value|Question):|—)/);
        isCentroid = true;
        questionType = "—: "
    }

    parts.forEach(part => {
        const [label, ...rest] = part.split(":");
        if (label == questionType) {
            if (label && rest.length > 0) {
                const value = rest.join(":").trim();
                const line = document.createElement("div"); // use div instead of span
                line.innerHTML = `<strong id="${cardKeywordsId}">${label.trim()}:</strong> ${value}`;
                container.appendChild(line);
            }
        } else {

            if (label && rest.length > 0) {
                const value = rest.join(":").trim();
                const line = document.createElement("div"); // use div instead of span
                line.innerHTML = `<strong>${label.trim()}:</strong> ${value}`;
                container.appendChild(line);
            }
        }
    });

    return container.innerHTML;
}

function saveCard(cardId, fieldName, predictedValue, index, issues) {
    const card = document.getElementById(cardId);
    const checkboxes = card.querySelectorAll(`input[name='${cardId}-confidence']:checked`);
    const selectedRanges = Array.from(checkboxes).map(cb => cb.value);

    if (!results[fieldName]) results[fieldName] = [];
    const existing = results[fieldName].filter(r => r.questionIndex !== index);
    existing.push({ questionIndex: index, predictedValue, selectedRanges, issues });
    results[fieldName] = existing;

}

function collapseCard(cardId, fieldName, predictedValue, index, tickets, kw, kw_id, originalKeywordsId, predictedSelectId) {
    const card = document.getElementById(cardId);
    const keyword_card_field = document.getElementById(kw_id);

let keywords = "";
const strongEl = document.getElementById(originalKeywordsId);

if (strongEl) {
  const parent = strongEl.parentElement;
  const label = strongEl.textContent || "";
  const allText = parent ? parent.textContent || "" : label;
  keywords = allText.replace(label, "").trim();
}

    const body = card.querySelector(".card-body");
    const status = "rejected"
    var new_keywords = "";

//    var new_keywords = kw
//    if (keyword_card_field.value != "") {
//        new_keywords = keyword_card_field.value;
//    }
    // Read selected predicted value (dropdown or text input)
    let finalPredictedValue = predictedValue;            // default to original
    let originalPredictedValue = predictedValue;         // always keep the original

    const pvEl = document.getElementById(predictedSelectId);
    if (pvEl && typeof pvEl.value === "string" && pvEl.value.trim() !== "") {
      const chosen = pvEl.value.trim();
      if (chosen !== predictedValue) {
        finalPredictedValue = chosen;                    // user changed it
      }
    }


    if (!results[fieldName]) results[fieldName] = [];
    const existing = results[fieldName].filter(r => r.questionIndex !== index);
    existing.push({
      questionIndex: index,
      predictedValue: finalPredictedValue,
      originalPredictedValue,
      tickets,
      new_keywords,
      keywords,
      status
    });

    results[fieldName] = existing;

    body.style.display = "none";
    card.classList.add("collapsed");
    card.children[0].style.background = "linear-gradient(90deg, #630909, #b40202)"
    card.style.opacity = "0.6";
}

function toggleIssues(listId) {
    const list = document.getElementById(listId);
    if (list) {
        list.style.display = list.style.display === "none" ? "block" : "none";
    }
}
function toggleKeywords(keywordsId) {
    const box = document.getElementById(keywordsId);
    if (box) {
        box.style.display = box.style.display === "none" ? "block" : "none";
    }
}

function collapseCardYes(cardId, fieldName, predictedValue, index, tickets, kw, kw_id, originalKeywordsId, predictedSelectId) {
    const card = document.getElementById(cardId);
    const keyword_card_field = document.getElementById(kw_id);
    const status = "approved";

let keywords = "";
const strongEl = document.getElementById(originalKeywordsId);

if (strongEl) {
  const parent = strongEl.parentElement;
  const label = strongEl.textContent || "";
  const allText = parent ? parent.textContent || "" : label;
  keywords = allText.replace(label, "").trim();
}

    const body = card.querySelector(".card-body");
    var new_keywords = "";
//    var new_keywords = kw

//    if (keyword_card_field.value != "") {
//        new_keywords = keyword_card_field.value;
//    }
        // Read selected predicted value (dropdown or text input)
    var finalPredictedValue = predictedValue;            // default to original
    var originalPredictedValue = predictedValue;         // always keep the original

    const pvEl = document.getElementById(predictedSelectId);
    if (pvEl && typeof pvEl.value === "string" && pvEl.value.trim() !== "") {
      const chosen = pvEl.value.trim();
      if (chosen !== predictedValue) {
        finalPredictedValue = chosen;                    // user changed it
      }
    }


    if (!results[fieldName]) results[fieldName] = [];
    const existing = results[fieldName].filter(r => r.questionIndex !== index);
    existing.push({
      questionIndex: index,
      predictedValue: finalPredictedValue,
      originalPredictedValue,        // NEW
      tickets,
      new_keywords,
      keywords,
      status
    });

    results[fieldName] = existing;

    body.style.display = "none";
    card.classList.add("collapsed");
    card.children[0].style.background = "linear-gradient(90deg, #3f7938, #5ac957)"
    card.style.opacity = "0.6";
}

function submitAll() {
    const userInput = document.getElementById("userNameInput").value;
    const monitor_label = document.getElementById("iterationMonitor").innerText;
    const issues_text = monitor_label.match(/#Issues:\s*(\d+)/);
    const questions = document.getElementById("iterationMonitor").innerText;
    const question_number = parseInt(questions.match(/Questions:\s*(\d+)/)[1], 10)
    const iteration_information = JSON.stringify(window.pageData.iteration_information);
    const issue_number = iteration_information["total_issue_count"] - iteration_information["orphan_count"]
    const total_approved = ((s) => { let t = 0; (function w(x) { if (Array.isArray(x)) return x.forEach(w); if (x && typeof x === 'object') for (const [k, v] of Object.entries(x)) k === 'tickets' && Array.isArray(v) && x.status === 'approved' ? t += v.flat(Infinity).length : w(v) })(s); return t })(results);

    if (userInput != "") {
        fetch("/confirmation_completed", {
            method: "POST",
            headers: { 'Content-Type': 'application/json', 'total-approved': total_approved, 'Question-Issue-Count': issue_number.toString(), 'user-name': userInput, 'q-number': question_number.toString(), 'iteration-information':iteration_information},
            body: JSON.stringify(results)
        })
            .then(res => res.json())
            .then(() => {
                window.location.href = "/";
            })
            .catch();
    }
}
function generateQuestions() {
    fetch("/process_csv", { method: "GET", headers: { 'Content-Type': 'application/json' } })
        .then(res => res.json())
        .then(json => renderQuestions(json));
}

document.getElementById("submitAll").addEventListener("click", submitAll);
document.getElementById("backToCsv").addEventListener("click", () => {
    window.history.back();
});

document.addEventListener("DOMContentLoaded", function () {
    generateQuestions()
});

// --- Verification UI wiring ---
const verifyBtn = document.getElementById('verifyUserBtn');
const verifyStatus = document.getElementById('verifyStatus');
const submitAllBtn = document.getElementById('submitAll');
const userEl = document.getElementById('userNameInput');
const passEl = document.getElementById('userPasswordInput');
const jiraUrlEl = document.getElementById('jiraUrl');


verifyBtn?.addEventListener('click', verifyJiraUser);

// OPTIONAL: re-require verification if user changes the selected username
userEl?.addEventListener('change', () => {
    submitAllBtn.disabled = true;
    verifyStatus.textContent = '';
});

async function verifyJiraUser() {
    submitAllBtn.disabled = true; // lock until success
    verifyStatus.classList.remove('text-success', 'text-danger');
    verifyStatus.textContent = 'Verifying…';

    const payload = {
        jira_url: (jiraUrlEl?.value || '').trim(),
        username: (userEl?.value || '').trim(),
        password: (passEl?.value || '').trim() // API token for Jira Cloud
    };

    // Basic client-side checks
    if (!payload.username || !payload.password) {
        verifyStatus.classList.add('text-danger');
        verifyStatus.textContent = 'Username and password/token are required.';
        return;
    }
    if (!payload.jira_url) {
        verifyStatus.classList.add('text-danger');
        verifyStatus.textContent = 'JIRA URL missing on this page.';
        return;
    }

    try {
        const res = await fetch('/auth/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            credentials: 'same-origin'
        });

        const json = await res.json();
        if (res.ok && json.ok) {
            verifyStatus.classList.add('text-success');
            verifyStatus.textContent = 'Verified ✔';
            // Lock fields after success (optional)
            userEl.disabled = true;
            passEl.value = '';
            passEl.disabled = true;
            submitAllBtn.disabled = false; // ✅ enable the submit button
        } else {
            verifyStatus.classList.add('text-danger');
            verifyStatus.textContent = json.error ? `Failed: ${json.error}` : 'Verification failed.';
            submitAllBtn.disabled = true;
        }
    } catch (err) {
        verifyStatus.classList.add('text-danger');
        verifyStatus.textContent = `Error: ${err?.message || err}`;
        submitAllBtn.disabled = true;
    }
}