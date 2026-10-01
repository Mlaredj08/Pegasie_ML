/* JFIP Pro UI – Backend‑wired orchestration
 * Replaces SAMPLE_DATA with live data from the backend (same shape used by confirmation.js).
 * - Fetches /process_csv on load
 * - Groups cards by field_name (tabs) and renders clusters
 * - Adds compact debug metrics (cohesion, density, centroid) per card
 * - Lets user expand issues and (NEW) deselect any issues via checkboxes;
 *   when clicking YES, only the checked issues are included in the final JSON.
 * - Builds the same results structure produced by confirmation.js
 * - Submits to /confirmation_completed and redirects to "/"
 */


let results = {};
const fieldStats = {};
const questionState = {};
let overall = { total: 0, completed: 0, yes: 0, no: 0, edited: 0 };

const els = {
  kIter: document.getElementById('k-iter'),
  kAvg: document.getElementById('k-avg'),
  kQst: document.getElementById('k-qst'),
  kTotal: document.getElementById('k-total'),
  tabs: document.getElementById('questionTabs'),
  tabsContent: document.getElementById('questionTabsContent'),
  sidebar: document.getElementById('progressSidebar'),
  toggleSidebar: document.getElementById('toggleSidebar'),
  toggleTableBtn: document.getElementById('toggleTableBtn'),
  closeSidebar: document.getElementById('closeSidebar'),
  psFields: document.getElementById('psFields'),
  overallPct: document.getElementById('overallPct'),
  overallBar: document.getElementById('overallBar'),
  overallCounts: document.getElementById('overallCounts'),
  iterationTable: document.getElementById('iterationTable'),
  submit: document.getElementById('submitAll'),
  back: document.getElementById('backBtn'),
  loadIteration: document.getElementById('loadIteration'),
  runIteration: document.getElementById('runIteration'),
  saveIteration: document.getElementById('saveIteration'),
};

// --- Drawer wiring
els.toggleSidebar?.addEventListener('click', () => {
  els.sidebar.classList.toggle('open');
  document.body.classList.toggle('sidebar-open', els.sidebar.classList.contains('open'));
});
els.closeSidebar?.addEventListener('click', () => {
  els.sidebar.classList.remove('open');
  document.body.classList.remove('sidebar-open');
});
els.toggleTableBtn?.addEventListener('click', () => toggleTable());

// --- Buttons
els.back?.addEventListener('click', () => history.back());
els.submit?.addEventListener('click', handleSubmit);
// We'll not bind runIteration here because the HTML attaches a wrapper that shows/hides the modal.
// els.runIteration?.addEventListener('click', handleNextIteration);
els.loadIteration?.addEventListener('click', () => {
  loadFromBackend('/process_csv');
});

document.addEventListener('DOMContentLoaded', () => {
  loadFromBackend('/process_csv');
  loadFieldSummary();
  setTableCollapsed(true);
});


function initializeTooltips(){
  const toggles = document.querySelectorAll('[data-bs-placement="top"]');
  toggles.forEach(element => {
    const field = element.getAttribute('name');
    const infoDict = globalParams.best_model_per_field[field]
    const mlMode = infoDict.ml_model;
    let optimalConfidence = (100 * infoDict.optimal_confidence).toFixed(2);
    optimalConfidence = infoDict.optimal_confidence == 1 ? "100" : optimalConfidence;
    let f1Score = (100 * infoDict.optimal_confidence_f1_score).toFixed(2);
    f1Score = infoDict.optimal_confidence_f1_score == 1 ? "100" : f1Score;
    const accuracyPerConfidence = infoDict.accuracy_per_confidence;
    const [firstKey, firstValue] = Object.entries(accuracyPerConfidence)[0];
    const testDataSize = firstValue.test_data_size;
    let tooltipDesc = `ML Model: ${mlMode}, Optimal Confidence: ${optimalConfidence}%, Estimated F1-Score: ${f1Score}%`;
    tooltipDesc += `, Test Data Size: ${testDataSize}`;
    const toolTip = document.getElementById(element.id);
    const tooltipDescHtml = tooltipDesc.replaceAll(", ", "<br>")
    toolTip.setAttribute('data-bs-html', true)
    toolTip.setAttribute('data-bs-title', `<div class="text-start">${tooltipDescHtml}</div>`);
    const tabTooltip = new bootstrap.Tooltip(toolTip, { trigger: 'hover' });
  });
}

/* ---------- Table collapse helpers ---------- */
function ensureIterationTableWrapped(){
  const table = els.iterationTable;
  if(!table) return null;
  if (table.parentElement && table.parentElement.classList.contains('table-scrollwrap')){
    return table.parentElement;
  }
  const wrap = document.createElement('div');
  wrap.id = 'iterationScrollWrap';
  wrap.className = 'table-scrollwrap';
  table.parentNode.insertBefore(wrap, table);
  wrap.appendChild(table);
  return wrap;
}
function enforceTableScrollIfNeeded(){
  const table = els.iterationTable;
  if(!table) return;
  const wrap = ensureIterationTableWrapped();
  const tbody = table.tBodies && table.tBodies[0];
  if(!wrap || !tbody) return;
  const rows = Array.from(tbody.rows).filter(r => !r.classList.contains('keep-visible'));
  if(rows.length > 3){
    const heights = rows.slice(0,3).map(r => {
      if(getComputedStyle(r).display === 'none'){ r.style.display = 'table-row'; }
      const prev = r.style.display;
      const h = r.getBoundingClientRect().height || 36;
      r.style.display = prev;
      return h;
    });
    wrap.style.maxHeight = Math.round(heights.reduce((a,b)=>a+b,0) + 2) + 'px';
  }else{
    wrap.style.maxHeight = '';
  }
}
function setTableCollapsed(collapsed){
  if(!els.iterationTable) return;
  els.iterationTable.classList.toggle('table-collapsed', collapsed);
}
function toggleTable(){
  if(!els.iterationTable) return;
  const wasCollapsed = els.iterationTable.classList.contains('table-collapsed');
  setTableCollapsed(!wasCollapsed);
  const nowCollapsed = els.iterationTable.classList.contains('table-collapsed');
  if(!nowCollapsed){
    enforceTableScrollIfNeeded();
  }
}

/* ---------- Update cluster item ---------- */
function updateCluster(checkbox) {
    const parentElement = checkbox.closest('.qc');
    const checkboxes = parentElement.querySelectorAll('.form-check-input');
    const checkedCheckboxes = parentElement.querySelectorAll('.form-check-input:checked');
    if (parentElement.classList.contains('approved')) {
        if(checkedCheckboxes.length > 0){
            parentElement.querySelector('.act-yes').click();
            parentElement.querySelector('.act-yes').click();
            parentElement.querySelector('.toggle-btn').click();
        }
        else{
            checkboxes.forEach(checkbox => { checkbox.checked = true; });
            parentElement.querySelector('.act-yes').click();
            parentElement.querySelector('.toggle-btn').click();
        }
    }
    else if (parentElement.classList.contains('rejected')) {
        if(checkedCheckboxes.length > 0){
            parentElement.querySelector('.act-no').click();
            parentElement.querySelector('.act-no').click();
            parentElement.querySelector('.toggle-btn').click();
        }
        else{
            checkboxes.forEach(checkbox => { checkbox.checked = true; });
            parentElement.querySelector('.act-no').click();
            parentElement.querySelector('.toggle-btn').click();
        }
    }
    else {
        if(checkedCheckboxes.length == 0){
            checkboxes.forEach(checkbox => { checkbox.checked = true; });
        }
    }
}

function updateSelectedCountPerField(){
    //console.log(JSON.stringify(results));
    for (const [targetField, questions] of Object.entries(results)) {
      let acceptedPredictions = 0;
      let rejectedPredictions = 0;
      questions.forEach(question => {
        acceptedPredictions += question.status == "approved" ? question.tickets.length : 0;
        rejectedPredictions += question.status == "rejected" ? question.tickets.length : 0;
      });
      $(`.${targetField}SelectedCount`).html(acceptedPredictions > 0 ? acceptedPredictions : "");
      $(`.${targetField}RejectedCount`).html(rejectedPredictions > 0 ? rejectedPredictions : "");
    }
}
/* ---------- Data loading ---------- */
async function loadFromBackend(endpoint){
  try{
    // Use provided endpoint; default to /process_csv
    const url = endpoint || '/process_csv';
    const res = await fetch(url, { method: 'GET', headers: { 'Content-Type': 'application/json' } });
    const json = await res.json();
    loadJson(json);
    return json; // explicitly return so callers can await completion
  }catch(err){
    console.error('Failed to load data:', err);
    alert('Could not load questions from backend.');
    throw err;
  }
}

function loadJson(data){
  // Reset state
  Object.keys(fieldStats).forEach(k => delete fieldStats[k]);
  Object.keys(questionState).forEach(k => delete questionState[k]);
  results = {};
  overall = { total: 0, completed: 0, yes: 0, no: 0, edited: 0 };



  renderQuestions(data);
  restoreSavedQuestion();
  buildSidebar(Object.keys(fieldStats));
  refreshAllProgress();
  // Disable submit until at least one question is approved
  updateSubmitButtonState();
  $(els.saveIteration).addClass('disabled').attr('aria-disabled', 'true');
}

/* ---------- Restoring saved state ---------- */
function restoreSavedQuestion() {
  if(Object.keys( window.pageData.saved_review_state).length === 0){ return; }

  const savedTallies = window.pageData.saved_review_state.review_page_tallies ?? {};
  const savedTalliesPerTab = window.pageData.saved_review_state.review_page_tallies_per_tab ?? {};
  const disabledCheckboxes = window.pageData.saved_review_state.disabled_checkboxes ?? {};
  const isSameIter = savedTallies.kIterTally == $(els.kIter).html();
  const isSameQst = savedTallies.kQstTally == $(els.kQst).html();
  const isSameTotal = savedTallies.kTotalTally == $(els.kTotal).html();
  //const isSameTallies = isSameIter && isSameQst && isSameTotal;
  const talliesPerTab = getTabTallies()
  const isSameTallies = isSameIter;  // TODO: check tally per field
  if(!isSameTallies){
    const errMsg = "Saved state was not restored: page has changed.";
    console.error(errMsg);
    alert(errMsg);
    return;
  }

  const savedTargetFields = window.pageData.saved_review_state.target_fields ?? [];
  savedTargetFields.forEach((element, index, array) => {
    const fieldName = element.field_name;
    const isUnchanged = checkTalliesAreUnchanged(talliesPerTab, savedTalliesPerTab, fieldName);
    if(isUnchanged){
        const yesList = element.predictions;
        const noList = element.rejected_predictions;
        restoreSavedReviewState(yesList, true);
        restoreSavedReviewState(noList, false);
    }
  });

  // Restore disabled (pushed) li
  disabledCheckboxes.forEach((item) => {
    const disabledCheckboxId = item.checkboxId;
    console.log(`Disabling checkbox ${disabledCheckboxId} ...`);
    $(`#${disabledCheckboxId}`).closest('li').addClass('disabled').find('*').prop('disabled', true);
    $(`#${disabledCheckboxId}`).closest('li').css('opacity', '0.5');
    // Just in case the clustering  changes
    if (!$(`#${disabledCheckboxId}`).length) {
      // "checkboxId": "list-team-cent-FBEZ-221-cb-FBEZ-222",
      console.log(`Checkbox ${disabledCheckboxId} was not found.`)
      const prefix = item.checkboxId.split('-cent-')[0];
      const issueKey = item.checkboxId.split("-cb-")[1];
      const disabledCheckbox = $(`[id^="${prefix}"][id$="${issueKey}"]`)
      disabledCheckbox.closest('li').addClass('disabled').find('*').prop('disabled', true);
      disabledCheckbox.closest('li').css('opacity', '0.5');
    }
  });

}

function checkTalliesAreUnchanged(talliesPerTab, savedTalliesPerTab, fieldName){
    const tallies = talliesPerTab[`${fieldName}-tab`];
    const savedTallies = savedTalliesPerTab[`${fieldName}-tab`];
    return savedTallies.startsWith(tallies);
}
function restoreSavedReviewState(predictions, isYes=true){
    const questionIdIssueKeySeparator = '|';
    predictions.forEach((item, index, array) => {
      const questionIds = item.tagged_issue_keys ?? []
      let cardIds = questionIds.map(str => str.split(questionIdIssueKeySeparator)[0]);
      cardIds = [...new Set(cardIds)];

      // Restore Yes/No buttons
      cardIds.forEach((cardId, index, array) => {
        // Unselect all checkboxes
        $(`#${cardId}`).find(':checkbox').prop('checked', false);
        if(isYes) {
          $(`#${cardId}`).find(".act-yes").click();
        }
        else {
          const btnElt = $(`#${cardId}`).find(".act-no");
          if (btnElt.length) {
            btnElt.click();
          }
        }
      });

      // Restore Checkboxes
      questionIds.forEach((questionId, index, array) => {
        const issueKey = questionId.split(questionIdIssueKeySeparator)[1];
        const cardId = questionId.split(questionIdIssueKeySeparator)[0];
        const checkboxElt =  $(`#${cardId}`).find(`input[type="checkbox"][data-issue^="${issueKey}_"]`);
        if (checkboxElt.length) {
          checkboxElt.click();
        }
      });
    });
}
/* ---------- Rendering ---------- */
function renderQuestions(data){
  els.tabs.innerHTML = '';
  els.tabsContent.innerHTML = '';

  const toFlat = (x) => Array.isArray(x) ? x.flat(Infinity) : [];
  const toAvg = (arr) => {
    const nums = toFlat(arr).filter(n => typeof n === 'number' && !isNaN(n));
    if (!nums.length) return null;
    const sum = nums.reduce((a, b) => a + b, 0);
    return (sum / nums.length);
  };

  const grouped = {};
  const orphaned = [];
  for (const [predictedValue, questions] of Object.entries(data || {})) {
    if (predictedValue === '__meta') continue;
    if (!Array.isArray(questions)) continue;
    for (const q of questions){
      const isOrphaned =
        String(q.question || '').trim().toUpperCase().startsWith('ORPHANED') ||
        q.is_orphan === true;

      if (isOrphaned){
        const conf = toAvg(q.confidence);
        const kws  = Array.isArray(q.keywords) ? q.keywords : [];
        const issuesArr = Array.isArray(q.list_of_issues)
          ? (Array.isArray(q.list_of_issues[0]) ? q.list_of_issues[0] : q.list_of_issues)
          : [];
        if(issuesArr.length === 0){
          orphaned.push({
            predictedValue,
            targetedField: q.field_name,
            confidence: conf,
            keywords: kws,
            issue: '—',
            orphan_reason: q.orphan_reason ?? null
          });
        }else{
          for (const issue of issuesArr){
            orphaned.push({
              predictedValue,
              targetedField: q.field_name,
              confidence: conf,
              keywords: kws,
              issue: issue || '—',
              orphan_reason: q.orphan_reason ?? null
            });
          }
        }
        continue;
      }

      const fieldName = q.field_name || 'Other';
      if (!grouped[fieldName]) grouped[fieldName] = [];
      grouped[fieldName].push(Object.assign({ predictedValue }, q));
    }
  }
  function headerTextFromQuestion(qstr = '') {
    const match = qstr.match(/—\s*:\s*(.+)$/);
    return match ? match[1].trim() : qstr.trim();
  }

  const order = (data && data.__meta && Array.isArray(data.__meta.field_order))
    ? data.__meta.field_order
    : Object.keys(grouped);

  let qIndex = 0;
  order.forEach((fieldName, tIdx) => {
    const list = grouped[fieldName] || [];
    if(!list.length) return;

    if(!fieldStats[fieldName]) fieldStats[fieldName] = { total: 0, completed: 0, yes: 0, no: 0, edited: 0 };
    let predictionCount = 0;
    list.forEach(item => { item.list_of_issues.forEach(predictions => { predictionCount += predictions.length; }); });
    //const cardSpan = `<span class="badge text-bg-info">${list.length}</span>`;
    let cardSpan = `<span class="badge text-bg-info" data-bs-toggle="tooltip" title="Questions">${list.length}</span>`;
    cardSpan += `<span class="badge text-bg-warning" data-bs-toggle="tooltip" title="Predictions">${predictionCount}</span>`;
    cardSpan += `<span class="badge text-bg-success ${fieldName}SelectedCount" data-bs-toggle="tooltip" title="Accepted"></span>`;
    cardSpan += `<span class="badge text-bg-danger ${fieldName}RejectedCount" data-bs-toggle="tooltip" title="Rejected"></span>`;
    const capFieldName = fieldName.charAt(0).toUpperCase() + fieldName.slice(1);
    const safe = cssSafe(fieldName);
    const tabId = `${safe}-tab`;
    const paneId = `${safe}-pane`;
    const tooltipId = `${safe}-tooltip`
    const li = document.createElement('li');
    li.className = 'nav-item pe-1 pt-2'; li.role='presentation';
//    li.innerHTML = `<button class="nav-link border border-secondary rounded ${tIdx===0 ? 'active':''}" id="${tabId}" data-bs-toggle="tab" data-bs-target="#${paneId}" type="button" role="tab" aria-controls="${paneId}" aria-selected="${tIdx===0}">${escapeHtml(capFieldName)} ${cardSpan}</button>`;
    let innerHtml = `<button class="nav-link border border-secondary rounded ${tIdx===0 ? 'active':''}" id="${tabId}" data-bs-toggle="tab" data-bs-target="#${paneId}" type="button" role="tab" aria-controls="${paneId}" aria-selected="${tIdx===0}">${escapeHtml(capFieldName)} ${cardSpan}</button>`;
    li.innerHTML = `<span id="${tooltipId}" name="${safe}" data-bs-toggle="tooltip" data-bs-placement="top">${innerHtml}</span>`;
    els.tabs.appendChild(li);

    const pane = document.createElement('div');
    pane.className = `tab-pane fade ${tIdx===0 ? 'show active':''}`;
    pane.id = paneId; pane.role='tabpanel';
    const container = document.createElement('div');
    container.className = 'row g-3';
    pane.appendChild(container);
    els.tabsContent.appendChild(pane);

    list.forEach((q, idx) => {
      const clusterCentroid = q.cluster_centroid;
//      const cardId = `q-${qIndex}`;
//      const listId = `list-${qIndex}`;
//      const selectId = `select-${qIndex}`;
      const cardId = `q-${fieldName}-${clusterCentroid}`;
      const listId = `list-${fieldName}-cent-${clusterCentroid}`;
      const selectId = `select-${fieldName}-cent-${clusterCentroid}`;


      fieldStats[fieldName].total += 1;
      overall.total += 1;
      questionState[cardId] = { fieldName, answer: null, dirty: false };

      const col = document.createElement('div');
      col.className = 'col-12';

      const issues = Array.isArray(q.list_of_issues) ? (Array.isArray(q.list_of_issues[0]) ? q.list_of_issues[0] : q.list_of_issues)
        : [];

      const issuesChips = (Array.isArray(q.list_of_issues) ? (Array.isArray(q.list_of_issues[0]) ? q.list_of_issues[0] : q.list_of_issues)
        : [])
        .map(k => `<span class="chip">${escapeHtml(String(k), k.includes(q.cluster_centroid + "_"))}</span>`).join(' ');

      const simStyle = Object.hasOwn(q, "similarity_score") ? "" : 'style="display: none;"';
      const denStyle = Object.hasOwn(q, "similarity_density") ? "" : 'style="display: none;"';
      col.innerHTML = `
        <div class="qc" id="${cardId}">
          <div class="qc-hd">
            <div class="me-2">
              <div class="mb-1"><strong>${escapeHtml(headerTextFromQuestion(q.question || ''))}</strong></div>
              <span hidden id="${cardId}_predicted_value">${escapeHtml(q.predictedValue || '')}</span>
              <div class="meta">#Issues: ${Number(q.cluster_issues_count ?? issues.length)}</div>
            </div>
            <button class="btn btn-sm btn-outline-secondary toggle-btn" title="Collapse/expand"><i class="bi bi-caret-down"></i></button>
          </div>
          <div class="qc-bd">
            <div class="mb-2">${issuesChips}</div>

            <div class="d-flex align-items-center justify-content-between mb-2 actions">
              <div class="btn-group">
                <!--button class="btn btn-success btn-sm act-yes"><i class="bi bi-check2-circle"></i> Yes</button-->
                <button class="btn btn-outline-success btn-sm act-yes"><i class="bi bi-check2-circle"></i> Yes</button>
                <button class="btn btn-outline-danger btn-sm act-no"><i class="bi bi-x-circle"></i> No</button>
              </div>
              <button class="btn btn-sm btn-outline-secondary act-toggle">+</button>
            </div>

            <ul id="${listId}" class="mb-2" style="display:none; padding-left:1.1rem">
              ${issues.map((it, i) => `
                <li class="form-check">
                  <!--input class="form-check-input" type="checkbox" id="${listId}-cb-${i}" data-issue="${escapeHtml(it)}" onchange="updateCluster(this)" checked-->
                  <!--label class="form-check-label" for="${listId}-cb-${i}">${escapeHtml(it, it.includes(q.cluster_centroid + "_"))}</label-->
                  <input class="form-check-input" type="checkbox" id="${listId}-cb-${it.split('_')[0]}" data-issue="${escapeHtml(it)}" onchange="updateCluster(this)" checked>
                  <label class="form-check-label" for="${listId}-cb-${it.split('_')[0]}">${escapeHtml(it, it.includes(q.cluster_centroid + "_"))}</label>
                </li>`).join('')}
              ${!issues.length ? '<li class="text-muted">— no issues —</li>' : ''}
            </ul>
          </div>

          <div class="post p-2" style="display:none">
            <label class="form-label mb-1" for="${selectId}">Select new value:</label>
            ${renderValueControl(selectId, data, fieldName, q.predictedValue, cardId)}
          </div>

          <div class="post p-2" style="display:block; border-top:1px dashed #e5e7eb; background:#fafafa">
            <div class="d-flex align-items-center gap-3 flex-wrap small">
              <div ${denStyle}><strong>Cohesion:</strong> ${formatNumberOrDash(q.similarity_cohesion,3)}</div>
              <div ${denStyle}><strong>Density:</strong> ${formatNumberOrDash(q.similarity_density,3)}</div>
              <div ${simStyle}><strong>Similarity:</strong> ${formatNumberOrDash(q.similarity_score,3)}</div>
              <div><strong>Centroid:</strong> ${escapeHtml(q.cluster_centroid || '—')}</div>
            </div>
          </div>
        </div>`;

      const card = col.querySelector(`#${cardId}`);
      col.querySelector('.toggle-btn')?.addEventListener('click', () => reopenCard(cardId));
      col.querySelector('.act-toggle')?.addEventListener('click', () => toggleIssues(listId));

      col.querySelectorAll('.chip').forEach(ch => {
        ch.addEventListener('click', (e) => {
          e.stopPropagation();
          ch.classList.toggle('inactive');
          recomputeDirty(card);
        });
      });

      col.querySelector('.act-yes')?.addEventListener('click', (ev) => {

        ev.stopPropagation();
        const selectedIssues = getCheckedIssues(listId);
        const isApproved = card.matches('.approved');

        if(isApproved) {
            ev.currentTarget.classList.replace("btn-success", "btn-outline-success");
            setQuestionAnswer(cardId, 'yes', true);
            // recomputeDirty(card); Not sure if this function is needed !!?
            saveResult(fieldName, cardId, null, null, null, null, null, null,
              true // isUndo
            );
            collapseCancel(cardId);
        }
        else {
            collapseYes(cardId);
            setQuestionAnswer(cardId, 'yes');
            recomputeDirty(card);
            ev.currentTarget.classList.replace("btn-outline-success", "btn-success");
            const noBtn = ev.currentTarget.nextElementSibling;
            noBtn.classList.replace("btn-danger", "btn-outline-danger");
            saveResult(fieldName, cardId,
              q.predictedValue || '',
              selectedIssues,
              extractKeywordsText(q.question||''),
              '',
              'approved',
              q.predictedValue || ''
            );
        }
        updateSelectedCountPerField();
      });

      col.querySelector('.act-no')?.addEventListener('click', (ev) => {

        ev.stopPropagation();
        const selectedIssues = getCheckedIssues(listId);
        const isRejected = card.matches('.rejected');

        if(isRejected) {
            ev.currentTarget.classList.replace("btn-danger", "btn-outline-danger");
            setQuestionAnswer(cardId, 'no', true);
            // recomputeDirty(card); Not sure if this function is needed !!?
            saveResult(fieldName, cardId, null, null, null, null, null, null,
              true // isUndo
            );
            collapseCancel(cardId);
        }
        else {
            collapseNo(cardId);
            setQuestionAnswer(cardId, 'no');
            const yesBtn = ev.currentTarget.previousElementSibling;
            yesBtn.classList.replace("btn-success", "btn-outline-success");
            ev.currentTarget.classList.replace("btn-outline-danger", "btn-danger");

            const sel = col.querySelector(`#${selectId}`);
            const newVal = sel && typeof sel.value === 'string' ? sel.value.trim() : '';

            saveResult(fieldName, cardId,
              newVal || (q.predictedValue || ''),
              selectedIssues,
              extractKeywordsText(q.question||''),
              newVal,
              'rejected',
              q.predictedValue || ''
            );
        }
        updateSelectedCountPerField();
      });

      container.appendChild(col);
      qIndex++;
    });
  });

  if(orphaned.length){
    const cardSpan = `<span class="badge text-bg-warning">${orphaned.length}</span>`;
    const li = document.createElement('li');
    li.className = 'nav-item pe-1 pt-2'; li.role='presentation';
    li.innerHTML = `<button class="nav-link border border-secondary rounded ${!Object.keys(fieldStats).length ? 'active':''}" id="orph-tab" data-bs-toggle="tab" data-bs-target="#orph-pane" type="button" role="tab" aria-controls="orph-pane" aria-selected="${!Object.keys(fieldStats).length}">Orphans ${cardSpan}</button>`;
    els.tabs.appendChild(li);

    const pane = document.createElement('div');
    pane.className = `tab-pane fade ${!Object.keys(fieldStats).length ? 'show active':''}`;
    pane.id='orph-pane'; pane.role='tabpanel';
    pane.innerHTML = `
      <div class="kard">
        <div class="d-flex align-items-center justify-content-between">
          <h6 class="mb-0">Orphaned Predictions Summary</h6>
         <!--span class="badge text-bg-info">${orphaned.length}</span-->
        </div>
        <div class="table-responsive mt-2">
          <table class="table table-sm">
            <thead class="table-light">
              <tr>
                <th>Predicted Value</th>
                <th>Targeted field</th>
                <th>confidence</th>
                <th>keywords</th>
                <th>issue</th>
              </tr>
            </thead>
            <tbody>
              ${orphaned.map(o => `
                <tr>
                  <td>${escapeHtml(o.predictedValue)}</td>
                  <td>${escapeHtml(o.targetedField)}</td>
                  <td>${o.confidence == null ? "—" : Number(o.confidence).toFixed(2)}</td>
                  <td>${o.keywords?.length ? o.keywords.map(escapeHtml).join(', ') : '—'}</td>
                  <td>${escapeHtml(o.issue)}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
    els.tabsContent.appendChild(pane);
  }

  const notPredictable = (data && data.__meta && Array.isArray(data.__meta.not_predictable))
    ? data.__meta.not_predictable : [];
  if(notPredictable.length){
    const npBadge = `<span class="badge text-bg-warning">${notPredictable.length}</span>`;
    const npLi = document.createElement('li');
    npLi.className = 'nav-item pe-1 pt-2'; npLi.role='presentation';
    const npActive = !Object.keys(fieldStats).length && !orphaned.length;
    npLi.innerHTML = `<button class="nav-link border border-secondary rounded ${npActive ? 'active':''}" id="notpred-tab" data-bs-toggle="tab" data-bs-target="#notpred-pane" type="button" role="tab" aria-controls="notpred-pane" aria-selected="${npActive}">Empty ${npBadge}</button>`;
    els.tabs.appendChild(npLi);

    const npPane = document.createElement('div');
    npPane.className = `tab-pane fade ${npActive ? 'show active':''}`;
    npPane.id='notpred-pane'; npPane.role='tabpanel';
    npPane.innerHTML = `
      <div class="kard">
        <div class="d-flex align-items-center justify-content-between">
          <h6 class="mb-0">Not Predictable Yet</h6>
        </div>
        <p class="text-muted small mt-1 mb-2">These issues had empty or missing predicted values and were excluded from clustering.</p>
        <div class="table-responsive mt-2">
          <table class="table table-sm">
            <thead class="table-light">
              <tr>
                <th>Issue</th>
                <th>Summary</th>
                <th>Target Field</th>
                <th>Prediction</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              ${notPredictable.map(np => `
                <tr>
                  <td>${escapeHtml(np.key)}</td>
                  <td>${escapeHtml(np.summary)}</td>
                  <td>${escapeHtml(np.field)}</td>
                  <td>${escapeHtml(np.prediction)}</td>
                  <td>${np.confidence == null ? "—" : Number(np.confidence).toFixed(3)}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
    els.tabsContent.appendChild(npPane);
  }

  const rejectedPredictions = (data && data.__meta && Array.isArray(data.__meta.rejected_predictions))
    ? data.__meta.rejected_predictions : [];
  if(rejectedPredictions.length){
    const npBadge = `<span class="badge text-bg-danger">${rejectedPredictions.length}</span>`;
    const npLi = document.createElement('li');
    npLi.className = 'nav-item pe-1 pt-2'; npLi.role='presentation';
    const npActive = !Object.keys(fieldStats).length && !orphaned.length;
    npLi.innerHTML = `<button class="nav-link border border-secondary rounded ${npActive ? 'active':''}" id="reject-tab" data-bs-toggle="tab" data-bs-target="#reject-pane" type="button" role="tab" aria-controls="reject-pane" aria-selected="${npActive}">Rejected ${npBadge}</button>`;
    els.tabs.appendChild(npLi);

    const npPane = document.createElement('div');
    npPane.className = `tab-pane fade ${npActive ? 'show active':''}`;
    npPane.id='reject-pane'; npPane.role='tabpanel';
    npPane.innerHTML = `
      <div class="kard">
        <div class="d-flex align-items-center justify-content-between">
          <h6 class="mb-0">Previously Rejected Predictions</h6>
        </div>
        <p class="text-muted small mt-1 mb-2"></p>
        <div class="table-responsive mt-2">
          <table class="table table-sm">
            <thead class="table-light">
              <tr>
                <th>Issue</th>
                <th>Summary</th>
                <th>Target Field</th>
                <th>Prediction</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              ${rejectedPredictions.map(np => `
                <tr>
                  <td>${escapeHtml(np.key)}</td>
                  <td>${escapeHtml(np.summary)}</td>
                  <td>${escapeHtml(np.field)}</td>
                  <td>${escapeHtml(np.prediction)}</td>
                  <td>${escapeHtml(np.confidence)}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
    els.tabsContent.appendChild(npPane);
  }

  const unconfidentPredictions = (data && data.__meta && Array.isArray(data.__meta.unconfident_predictions))
    ? data.__meta.unconfident_predictions : [];
  if(unconfidentPredictions.length){
    const npBadge = `<span class="badge text-bg-warning">${unconfidentPredictions.length}</span>`;
    const npLi = document.createElement('li');
    npLi.className = 'nav-item pe-1 pt-2'; npLi.role='presentation';
    const npActive = !Object.keys(fieldStats).length && !orphaned.length;
    npLi.innerHTML = `<button class="nav-link border border-secondary rounded ${npActive ? 'active':''}" id="unconfident-tab" data-bs-toggle="tab" data-bs-target="#unconfident-pane" type="button" role="tab" aria-controls="unconfident-pane" aria-selected="${npActive}">Unconfident ${npBadge}</button>`;
    els.tabs.appendChild(npLi);

    const npPane = document.createElement('div');
    npPane.className = `tab-pane fade ${npActive ? 'show active':''}`;
    npPane.id='unconfident-pane'; npPane.role='tabpanel';
    npPane.innerHTML = `
      <div class="kard">
        <div class="d-flex align-items-center justify-content-between">
          <h6 class="mb-0">Unconfident Predictions</h6>
        </div>
        <p class="text-muted small mt-1 mb-2">Predictions with confidence scores below optimal confidence are excluded from the questionnaire clusters.</p>
        <div class="table-responsive mt-2">
          <table class="table table-sm">
            <thead class="table-light">
              <tr>
                <th>Issue</th>
                <th>Summary</th>
                <th>Target Field</th>
                <th>Prediction</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              ${unconfidentPredictions.map(np => `
                <tr>
                  <td>${escapeHtml(np.key)}</td>
                  <td>${escapeHtml(np.summary)}</td>
                  <td>${escapeHtml(np.field)}</td>
                  <td>${escapeHtml(np.prediction)}</td>
                  <td>${escapeHtml(np.confidence)}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
    els.tabsContent.appendChild(npPane);
  }
}

function renderValueControl(selectId, data, fieldName, predictedValue, cardId) {
  const list = (data && data.__meta && Array.isArray(data.__meta.field_values))
    ? (data.__meta.field_values.find(f => f.field_name === fieldName)?.list_of_values || [])
    : [];

  if (list.length) {
    const opts = list.map(v =>
      `<option value="${escapeHtml(v)}" ${v === predictedValue ? 'selected' : ''}>${escapeHtml(v)}</option>`
    ).join('');
    return `
      <select id="${selectId}"
              class="form-select form-select-sm"
              onchange="onSelectChange('${cardId}', '${selectId}')">
        <option value="" disabled selected hidden>Select...</option>
        ${opts}
      </select>`;
  }

  return `<input id="${selectId}" type="text" class="form-control form-control-sm"
                 value="${escapeHtml(predictedValue || '')}"
                 placeholder="Enter new value">`;
}

function onSelectChange(cardId, selectId) {
  const selectEl = document.getElementById(selectId);
  const newValue = selectEl.value;
  const originalValue = document.getElementById(cardId + "_predicted_value").textContent;

  const card = document.getElementById(cardId);
  if (card && originalValue != newValue) {
    recomputeDirty(card, true)
  }else{
    recomputeDirty(card)
  }
}

/* ---------- Progress (sidebar) ---------- */
function buildSidebar(fieldNames){
  els.psFields.innerHTML='';
  fieldNames.forEach(name => {
    const safe = cssSafe(name);
    const wrap = document.createElement('div');
    wrap.className = 'ps-item';
    wrap.innerHTML = `
      <div class="name">${escapeHtml(name)}</div>
      <div class="small text-muted mb-1" id="ps-meta-${safe}">
        completed 0 / ${fieldStats[name]?.total ?? 0} (Yes: 0 No: 0 Edited: 0)
      </div>
      <div class="ps-progress" aria-label="${escapeHtml(name)}">
        <div class="bar" id="ps-bar-${safe}" style="width:0%"></div>
      </div>`;

    els.psFields.appendChild(wrap);
  });
}
function setQuestionAnswer(cardId, answer, isUndo=false){
  const rec = questionState[cardId];
  if(!rec) return;
  const { fieldName } = rec;

  if(rec.answer === 'yes'){
    fieldStats[fieldName].yes = Math.max(0, fieldStats[fieldName].yes - 1);
    fieldStats[fieldName].completed = Math.max(0, fieldStats[fieldName].completed - 1);
    overall.yes = Math.max(0, overall.yes - 1);
    overall.completed = Math.max(0, overall.completed - 1);
  }else if(rec.answer === 'no'){
    fieldStats[fieldName].no = Math.max(0, fieldStats[fieldName].no - 1);
    fieldStats[fieldName].completed = Math.max(0, fieldStats[fieldName].completed - 1);
    overall.no = Math.max(0, overall.no - 1);
    overall.completed = Math.max(0, overall.completed - 1);
  }

  const inc = isUndo ? -1 : 1;
  if(answer === 'yes'){
    fieldStats[fieldName].yes += inc;
    overall.yes += inc;
  }else if(answer === 'no'){
    fieldStats[fieldName].no += inc;
    overall.no += inc;
  }
  fieldStats[fieldName].completed += inc;
  overall.completed += inc;

  rec.answer = answer;

  refreshFieldProgress(fieldName);
  refreshOverallProgress();
//  updateSubmitButtonState();
}

function updateDirtyState(cardId, isDirty){
  const rec = questionState[cardId];
  if(!rec) return;
  const { fieldName } = rec;

  if(!!rec.dirty === !!isDirty) return;

  if(isDirty){
    fieldStats[fieldName].edited += 1;
    overall.edited += 1;
  }else{
    fieldStats[fieldName].edited = Math.max(0, fieldStats[fieldName].edited - 1);
    overall.edited = Math.max(0, overall.edited - 1);
  }
  rec.dirty = !!isDirty;

  refreshFieldProgress(fieldName);
  refreshOverallProgress();
}

function refreshFieldProgress(fieldName){
  const { total, completed, yes, no, edited } = fieldStats[fieldName] || { total:0, completed:0, yes:0, no:0, edited:0 };
  const pct = total ? Math.round((completed/total)*100) : 0;
  const safe = cssSafe(fieldName);
  const bar = document.getElementById(`ps-bar-${safe}`);
  const meta = document.getElementById(`ps-meta-${safe}`);
  if(bar) bar.style.width = `${pct}%`;
  if(meta) meta.textContent = `completed ${completed} / ${total} (Yes: ${yes} No: ${no} Edited: ${edited})`;
}
function refreshOverallProgress(){
  const pct = overall.total ? Math.round((overall.completed/overall.total)*100) : 0;
  els.overallPct && (els.overallPct.textContent = `${pct}%`);
  els.overallCounts && (els.overallCounts.textContent =
    `completed ${overall.completed} / ${overall.total} (Yes: ${overall.yes} No: ${overall.no} Edited: ${overall.edited})`);
  if(els.overallBar) els.overallBar.style.width = `${pct}%`;
}

function refreshAllProgress(){
  Object.keys(fieldStats).forEach(refreshFieldProgress);
  refreshOverallProgress();
}

/* ---------- Card helpers ---------- */
function reopenCard(cardId){
  const card = document.getElementById(cardId);
  if(!card) return;
  card.classList.remove('collapsed');
  const bd = card.querySelector('.qc-bd'); if(bd) bd.style.display='block';
  const post = card.querySelector('.post'); if(post) post.style.display = (post.querySelector('select, input') ? 'block':'none');
}
function collapseCancel(cardId){
  const card = document.getElementById(cardId);
  if(!card) return; // ??!
  card.classList.add('collapsed');
  card.classList.remove('rejected', 'approved');
}
function collapseYes(cardId){
  const card = document.getElementById(cardId);
  if(!card) return;
  card.classList.add('collapsed','approved');
  card.classList.remove('rejected');
  const bd = card.querySelector('.qc-bd'); if(bd) bd.style.display = 'none';
  const post = card.querySelector('.post'); if(post) post.style.display='block';
  const formBits = post.querySelectorAll('label, select, input');
  formBits.forEach(el => el.style.display='none');
}
function collapseNo(cardId){
  const card = document.getElementById(cardId);
  if(!card) return;
  card.classList.add('collapsed','rejected');
  card.classList.remove('approved');
  const bd = card.querySelector('.qc-bd'); if(bd) bd.style.display = 'none';
  const post = card.querySelector('.post'); if(post) post.style.display='block';
}
function toggleIssues(listId){
  const el = document.getElementById(listId);
  if(el) el.style.display = (el.style.display === 'none' ? 'block' : 'none');
}
function getCheckedIssues(listId){
  const list = document.getElementById(listId);
  if(!list) return [];
  const cbs = list.querySelectorAll('input[type="checkbox"][data-issue]');
  return Array.from(cbs).filter(cb => cb.checked).map(cb => cb.getAttribute('data-issue'));
}
function cssSafe(s=''){ return String(s).replace(/[^a-zA-Z0-9_-]/g, '-'); }
function escapeHtml(s, isBold=false){
  retValue = String(s ?? '')
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
  return isBold ? `<b>${retValue}</b>` : retValue;
}
function extractKeywordsText(text=''){
  const m = text.match(/Keywords(?:\s+representing\s+the\s+group)?\s*:\s*(.*)$/i);
  return m ? m[1].trim() : '';
}
function formatNumberOrDash(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function recomputeDirty(card, force_true=false){
  if(!card) return;
  const hasInactiveChip = card.querySelectorAll('.chip.inactive').length > 0;
  const isDirty = force_true ? true : hasInactiveChip;
  card.classList.toggle('dirty', isDirty);
  updateDirtyState(card.id, isDirty);
}

/* ---------- Results ---------- */
function saveResult(fieldName, index, predictedValue, tickets, keywords, new_value, status, originalPredictedValue, isUndo=false){
  if(!results[fieldName]) results[fieldName] = [];
  const others = results[fieldName].filter(r => r.questionIndex !== index);
  if(!isUndo) {
      others.push({
        questionIndex: index,
        predictedValue,
        originalPredictedValue,
        tickets,
        new_keywords: "",
        keywords,
        status
      });
  }
  results[fieldName] = others;
  updateSubmitButtonState();
}

/* ---------- Submit ---------- */
async function handleNextIteration(isSaveIteration=false){
  const iteration_information = window.pageData.iteration_information;
  // k-user is a <div> like "User: name"; extract text instead of .value
  const userText = (document.getElementById('k-user')?.textContent || '—').replace(/^\s*User:\s*/,'').trim();
  const question_number = window.pageData.questionCount;
  const issue_number = iteration_information["total_issue_count"] - iteration_information["orphan_count"];

  try{
    const totalApproved = ((s) => {
      let t = 0;
      (function walk(x){
        if (Array.isArray(x)) return x.forEach(walk);
        if (x && typeof x === 'object'){
          for (const [k,v] of Object.entries(x)){
            if (k === 'tickets' && Array.isArray(v) && x.status === 'approved'){
              t += v.flat(Infinity).length;
            } else {
              walk(v);
            }
          }
        }
      })(s);
      return t;
    })(results);

    // These tallies are used to check the page hasn't changed before the saved state is restored.
    const talliesPerTab = getTabTallies();
    const tallies = {kIterTally: $(els.kIter).html(), kQstTally: $(els.kQst).html(), kTotalTally: $(els.kTotal).html()};
    const payload = {
      results,  // your current results object
      meta: {
        totalApproved,
        questionIssueCount: issue_number,
        userName: userText,
        qNumber: question_number,
        iterationInformation: iteration_information,
        project: globalParams.output_folder,
        isSaveIteration: isSaveIteration,
        tallies: tallies,
        talliesPerTab: talliesPerTab,
        disabledCheckboxes: isSaveIteration ? getCurrentDisabledCheckboxes() : {}
      }
    };

    const res1 = await fetch('/confirmation_completed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });


    const data1 = await res1.json().catch(()=>({}));
    if(!res1.ok){
      alert('Action failed.');
      return;
    }

    // Skip if Save Iteration button
    if(isSaveIteration){
      $(els.saveIteration).addClass('disabled').attr('aria-disabled', 'true');
      return;
    }

    let url = "/run_inference_iteration";
    url += "?db=" + globalParams.input_json;
    url += "&targetField=" + globalParams.inferred_fields;
    window.location.assign(url);

  }
  catch(err){
    console.error('Submit error', err);
    alert('There was an error submitting your confirmations.');
  }
}

function getCurrentDisabledCheckboxes() {
  disabledList = []
  $('li.disabled').each(function(index, element) {
    const checkboxId = $(this).children("input").first().attr("id");
    const questionId = $(this).closest('div.qc.approved').attr("id");
    console.log(`checkboxId: ${checkboxId}`);
    disabledList.push({checkboxId: checkboxId, questionId: questionId})
  });
  console.log(`disabledList: ${JSON.stringify(disabledList)}`);
  return disabledList;
}
async function handleSubmit(){
  // The actual submit logic is now in the inline script in confirm_predictions.html
  // This function is kept for backward compatibility but the HTML handler does the work
}

// Check if submit button should be enabled based on confirmed questions
function updateSubmitButtonState(){
  const hasApproved = Object.values(results || {}).some(arr =>
    Array.isArray(arr) && arr.some(r => r.status === 'approved')
  );
  if(els.submit) {
    els.submit.disabled = !hasApproved;
    els.submit.title = hasApproved ? 'Send confirmed predictions to Jira' : 'Confirm at least one question first';
    if(els.runIteration) els.runIteration.disabled = !hasApproved;
  }

  // Update Save Iteration button
  $(els.saveIteration).removeClass('disabled').attr('aria-disabled', 'false');
}


function renderPsFooter(summary) {
  const footer = document.getElementById("psFooter");
  if (!footer) return;

  const fields = summary.fields || {};
  const overall = summary.overall || { initial_total: 0, cumulative_approved: 0, completion_pct: 0 };

  // Build list items for each field
  const fieldItems = Object.entries(fields)
    .map(([name, vals]) => {
      const { cumulative_approved = 0, initial_total = 0, completion_pct = 0 } = vals;
      return `
        <li class="d-flex justify-content-between">
          <span>${name}</span>
          <strong>${cumulative_approved} / ${initial_total} (${completion_pct.toFixed(1)}%)</strong>
        </li>`;
    })
    .join("");

  // Add Overall as the last list item
  const overallItem = `
    <li class="d-flex justify-content-between border-top pt-1 mt-1">
      <span><strong>Overall</strong></span>
      <strong>${overall.cumulative_approved} / ${overall.initial_total} (${overall.completion_pct.toFixed(1)}%)</strong>
    </li>`;

  // Build the full footer
  footer.innerHTML = `
          <div class="d-flex justify-content-between small mb-1">
            <span>Overall</span> <strong id="overallPct">0%</strong>
        </div>
        <div class="ps-progress mb-1">
            <div class="bar" id="overallBar" style="width:0%"></div>
        </div>
        <div class="text-muted small" id="overallCounts">0 / 0 approved</div>
    <div class="ps-missing mt-3">
      <div class="text-uppercase text-muted small mb-2">Fields progress</div>
      <ul class="list-unstyled mb-0 small" id="missingTotalsList">
        ${fieldItems || "<li class='text-muted'>No fields found</li>"}
        ${overallItem}
      </ul>
    </div>
  `;
  els.overallPct    = footer.querySelector('#overallPct');
    els.overallBar    = footer.querySelector('#overallBar');
    els.overallCounts = footer.querySelector('#overallCounts');

// Now this will update the new nodes, not the removed ones
refreshOverallProgress();
}


/**
 * Example: Load dynamically from backend
 */
async function loadFieldSummary() {
  const project = globalParams.project;
  const infFields = globalParams.inferred_fields;
  const outFolder = globalParams.output_folder;
//  console.log(`project: ${project}`);
//  console.log(`inferredFields: ${infFields}`);
//  console.log(`outputFolder: ${outFolder}`);

  if (!infFields || (Array.isArray(infFields) && infFields.length === 0)) {
    console.log("No inferred fields available; skipping field summary.");
    return;
  }

  const res = await fetch(`/field_summary?project=${project}&infFields=${infFields}&outFolder=${outFolder}`, {
    method: "GET"
  });

  if (!res.ok) {
    console.error("Failed to load field summary");
    return;
  }
  const data = await res.json();
  renderPsFooter(data);
  initializeTooltips();
}

function getTabTallies() {
  let tabTallies = {};
  $('button.nav-link').each(function(index, element) {
    const tabId = $(element).attr('id')
    tabTallies[tabId] = $(element).text();
  });
  //console.log(`tabTallies: ${JSON.stringify(tabTallies)}`);
  return tabTallies;
}

