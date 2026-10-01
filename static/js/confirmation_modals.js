/* JFIP Pro UI – Modal Logic for confirm_predictions.html
 * Extracted from inline HTML script for better maintainability.
 * Depends on:
 *   - window.pageData (set in HTML via Jinja2)
 *   - globalParams (set in HTML via Jinja2)
 *   - results (from confirmation_predictions.js)
 *   - Bootstrap 5
 */

// --- Loading Modal ---
function showLoadingModal() {
  const el = document.getElementById('loadingOverlay');
  el.style.display = 'flex';
  document.body.setAttribute('aria-busy', 'true');
  document.body.style.cursor = 'progress';
}

function hideLoadingModal() {
  const el = document.getElementById('loadingOverlay');
  el.style.display = 'none';
  document.body.removeAttribute('aria-busy');
  document.body.style.cursor = '';
}

// If user returns via bfcache, ensure modal isn't stuck
window.addEventListener('pageshow', (e) => {
  if (e.persisted) hideLoadingModal();
});

// --- Utility: HTML escape (modal-specific, no isBold param) ---
function escapeHtmlModal(s) {
  return String(s ?? '')
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// --- Consolidation Modal Logic ---
const ConsolidationModal = (() => {
  let instance;
  let pendingIterationFile = null;
  let pushSucceeded = false;
  
  const els = {
    modal: document.getElementById('consolidationModal'),
    tablesContainer: document.getElementById('consolidationTablesContainer'),
    empty: document.getElementById('consolidationEmpty'),
    error: document.getElementById('consolidationError'),
    errorMsg: document.getElementById('consolidationErrorMsg'),
    filename: document.getElementById('consolidationFilename'),
    count: document.getElementById('consolidationCount'),
    totalIssues: document.getElementById('consolidationTotalIssues'),
    submitBtn: document.getElementById('consolidationSubmitBtn'),
    omittedSection: document.getElementById('omittedIssuesSection'),
    omittedCount: document.getElementById('omittedCount'),
    omittedBody: document.getElementById('omittedIssuesBody'),
    omittedLoading: document.getElementById('omittedLoading')
  };

  function countIssueKeysInType(predictions) {
    return predictions.reduce((sum, pred) => sum + (pred.issue_keys?.length || 0), 0);
  }

  function renderGroupedTables(predictionsByIssuetype, totalIssueKeys) {
    els.tablesContainer.innerHTML = '';
    
    const issueTypes = Object.keys(predictionsByIssuetype || {});
    
    if (issueTypes.length === 0) {
      els.tablesContainer.style.display = 'none';
      els.empty.style.display = 'block';
      els.error.style.display = 'none';
      els.count.textContent = '0';
      els.totalIssues.textContent = '0';
      return;
    }

    els.tablesContainer.style.display = 'block';
    els.empty.style.display = 'none';
    els.error.style.display = 'none';
    
    let totalPredictions = 0;
    
    issueTypes.sort();
    
    issueTypes.forEach(issueType => {
      const predictions = predictionsByIssuetype[issueType];
      const issueKeysCount = countIssueKeysInType(predictions);
      totalPredictions += predictions.length;
      
      const section = document.createElement('div');
      section.className = 'mb-4';
      
      const header = document.createElement('div');
      header.className = 'd-flex align-items-center justify-content-between mb-2 pb-2';
      header.style.borderBottom = '2px solid var(--brand)';
      header.innerHTML = `
        <div class="d-flex align-items-center gap-2">
          <i class="bi bi-bookmark-fill text-primary"></i>
          <h6 class="mb-0 fw-bold" style="color: var(--ink-900);">${escapeHtmlModal(issueType)}</h6>
        </div>
        <span class="badge bg-primary">${issueKeysCount} issue${issueKeysCount !== 1 ? 's' : ''}</span>
      `;
      section.appendChild(header);
      
      const tableWrapper = document.createElement('div');
      tableWrapper.className = 'table-responsive';
      tableWrapper.innerHTML = `
        <table class="table table-bordered table-striped table-hover mb-0">
          <thead class="table-light">
            <tr>
              <th style="min-width: 120px;"><i class="bi bi-tag me-1"></i>Field</th>
              <th style="min-width: 150px;"><i class="bi bi-arrow-right-circle me-1"></i>New Value</th>
              <th style="min-width: 200px;"><i class="bi bi-ticket-detailed me-1"></i>Issue Keys</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      `;
      
      const tbody = tableWrapper.querySelector('tbody');
      predictions.forEach(pred => {
        const row = document.createElement('tr');
        const issueKeysHtml = pred.issue_keys.map(key => 
          `<span class="badge bg-light text-dark border me-1 mb-1">${escapeHtmlModal(key)}</span>`
        ).join('');
        
        row.innerHTML = `
          <td><span class="badge bg-info text-dark">${escapeHtmlModal(pred.field)}</span></td>
          <td><span class="text-success fw-semibold">${escapeHtmlModal(pred.new_value)}</span></td>
          <td style="max-width: 300px;">${issueKeysHtml}</td>
        `;
        tbody.appendChild(row);
      });
      
      section.appendChild(tableWrapper);
      els.tablesContainer.appendChild(section);
    });
    
    els.count.textContent = totalPredictions;
    els.totalIssues.textContent = totalIssueKeys;
  }

  function showError(msg) {
    els.tablesContainer.style.display = 'none';
    els.empty.style.display = 'none';
    els.error.style.display = 'block';
    els.errorMsg.textContent = msg;
    els.count.textContent = '0';
    els.totalIssues.textContent = '0';
  }

  function getReasonDisplay(reason) {
    switch (reason) {
      case 'description_changed':
        return '<span class="badge bg-warning text-dark"><i class="bi bi-pencil-square me-1"></i>Description Changed</span>';
      case 'field_populated':
        return '<span class="badge bg-secondary"><i class="bi bi-check-circle me-1"></i>Field Populated</span>';
      case 'status_changed':
        return '<span class="badge bg-warning text-dark"><i class="bi bi-pencil-square me-1"></i>Status Changed</span>';
      default:
        return '<span class="badge bg-secondary">Unknown</span>';
    }
  }

  function renderOmittedIssues(omittedIssues) {
    els.omittedBody.innerHTML = '';
    
    if (!omittedIssues || omittedIssues.length === 0) {
      els.omittedSection.style.display = 'none';
      els.omittedCount.textContent = '0';
      return;
    }
    
    els.omittedSection.style.display = 'block';
    els.omittedCount.textContent = omittedIssues.length;
    
    omittedIssues.forEach(item => {
      const row = document.createElement('tr');
      row.dataset.issueKey = item.issue_key;
      row.dataset.field = item.field;
      row.innerHTML = `
        <td><span class="badge bg-light text-dark border">${escapeHtmlModal(item.issue_key)}</span></td>
        <td><span class="badge bg-info text-dark">${escapeHtmlModal(item.field)}</span></td>
        <td><span class="text-success">${escapeHtmlModal(item.predicted_value)}</span></td>
        <td><span class="text-warning fw-semibold">${escapeHtmlModal(item.current_value || '—')}</span></td>
        <td>${getReasonDisplay(item.reason)}</td>
        <td>
          <button class="btn btn-sm btn-outline-primary toggle-flag-btn" 
                  data-issue-key="${escapeHtmlModal(item.issue_key)}" 
                  data-field="${escapeHtmlModal(item.field)}"
                  data-reason="${escapeHtmlModal(item.reason)}"
                  data-state="ignored">
            <i class="bi bi-arrow-repeat me-1"></i>Overwrite
          </button>
        </td>
      `;
      els.omittedBody.appendChild(row);
    });

    document.querySelectorAll('.toggle-flag-btn').forEach(btn => {
      btn.addEventListener('click', handleToggleFlagClick);
    });
  }

  async function handleToggleFlagClick(event) {
    const btn = event.currentTarget;
    const issueKey = btn.dataset.issueKey;
    const field = btn.dataset.field;
    const reason = btn.dataset.reason;
    const filename = els.filename.textContent || '';
    
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    
    try {
      const res = await fetch('/toggle_ignore_flag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          filename: filename,
          issue_key: issueKey,
          field: field,
          reason: reason
        })
      });
      
      const data = await res.json();
      
      if (res.ok && data.success) {
        if (data.new_state === 'active') {
          btn.dataset.state = 'active';
          btn.className = 'btn btn-sm btn-outline-warning toggle-flag-btn';
          btn.innerHTML = '<i class="bi bi-arrow-counterclockwise me-1"></i>Undo';
        } else {
          btn.dataset.state = 'ignored';
          btn.className = 'btn btn-sm btn-outline-primary toggle-flag-btn';
          btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Overwrite';
        }
        btn.disabled = false;
      } else {
        alert('Error: ' + (data.error || 'Failed to toggle ignore flag'));
        btn.disabled = false;
        btn.innerHTML = originalText;
      }
    } catch (err) {
      console.error('Toggle flag error:', err);
      alert('Network error: Could not reach the server');
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }

  async function validateIssues(filename) {
    els.omittedLoading.style.display = 'block';
    els.omittedSection.style.display = 'none';
    
    try {
      const res = await fetch('/validate_push_issues', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename, db_path: globalParams.input_json || '' })
      });
      const data = await res.json();
      
      if (res.ok && data.omitted_issues) {
        renderOmittedIssues(data.omitted_issues);
      }
    } catch (err) {
      console.error('Validation error:', err);
    } finally {
      els.omittedLoading.style.display = 'none';
    }
  }

  return {
    async show() {
      if (!instance) {
        instance = new bootstrap.Modal(els.modal);
      }

      els.tablesContainer.innerHTML = '';
      els.filename.textContent = 'Loading...';
      els.tablesContainer.style.display = 'block';
      els.empty.style.display = 'none';
      els.error.style.display = 'none';
      els.omittedSection.style.display = 'none';
      els.omittedLoading.style.display = 'none';

      instance.show();

      try {
        const res = await fetch('/consolidate_iterations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project: globalParams.project || '', output_folder: globalParams.output_folder || '' })
        });
        const data = await res.json();

        if (!res.ok) {
          showError(data.error || 'Failed to consolidate iterations');
          return;
        }

        els.filename.textContent = data.filename || '';
        renderGroupedTables(data.predictions_by_issuetype || {}, data.total_issue_keys || 0);
        
        await validateIssues(data.filename || '');

      } catch (err) {
        console.error('Consolidation error:', err);
        showError('Network error: Could not reach the server');
      }
    },
    hide() {
      if (instance) instance.hide();
    },
    setPendingFile(filename) {
      pendingIterationFile = filename;
      pushSucceeded = false;
    },
    markPushSucceeded() {
      pushSucceeded = true;
    },
    async deletePendingFile() {
      if (!pendingIterationFile || pushSucceeded) {
        pendingIterationFile = null;
        return;
      }
      try {
        await fetch('/delete_iteration_file', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: pendingIterationFile })
        });
        console.log('[INFO] Deleted pending iteration file:', pendingIterationFile);
      } catch (err) {
        console.error('Failed to delete iteration file:', err);
      }
      //pendingIterationFile = null;
    }
  };
})();

// --- Push Summary Modal Logic ---
const PushSummaryModal = (() => {
  let instance;
  const modalEl = document.getElementById('pushSummaryModal');
  const contentEl = document.getElementById('pushSummaryContent');
  const okBtn = document.getElementById('pushSummaryOkBtn');

  function show(data) {
    if (!instance) instance = new bootstrap.Modal(modalEl);

    const success = data.success_count || 0;
    const failed = data.failed_count || 0;
    const total = success + failed;
    const allSuccess = failed === 0;

    let html = '';

    if (success > 0) {
      html += `
        <div class="d-flex align-items-center gap-2 mb-3">
          <i class="bi bi-check-circle-fill text-success" style="font-size:1.4rem"></i>
          <span class="fw-semibold">${success} of ${total} update${total !== 1 ? 's' : ''} pushed successfully</span>
        </div>`;
    }

    if (failed > 0) {
      const failedItems = data.failed_items || [];
      html += `
        <div class="d-flex align-items-center gap-2 mb-2">
          <i class="bi bi-exclamation-triangle-fill text-danger" style="font-size:1.4rem"></i>
          <span class="fw-semibold text-danger">${failed} update${failed !== 1 ? 's' : ''} could not be pushed</span>
        </div>
        <div class="mb-3">
          <button class="btn btn-sm btn-outline-secondary" type="button" data-bs-toggle="collapse" data-bs-target="#pushErrorDetails" aria-expanded="false" aria-controls="pushErrorDetails">
            <i class="bi bi-eye me-1"></i>View Details
          </button>
          <div class="collapse mt-2" id="pushErrorDetails">
            <div class="table-responsive">
              <table class="table table-bordered table-sm mb-0">
                <thead class="table-danger">
                  <tr>
                    <th>Issue Key</th>
                    <th>Field</th>
                    <th>HTTP Status</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  ${failedItems.map(item => `
                    <tr>
                      <td><span class="badge bg-light text-dark border">${escapeHtmlModal(item.issuekey)}</span></td>
                      <td><span class="badge bg-info text-dark">${escapeHtmlModal(item.field)}</span></td>
                      <td>${item.status_code ?? '—'}</td>
                      <td class="text-break small">${escapeHtmlModal(item.error)}</td>
                    </tr>`).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>`;
    }

    if (allSuccess && success > 0) {
      html += `
        <div class="alert alert-success mb-0">
          <i class="bi bi-patch-check me-1"></i>All updates were applied to Jira successfully.
        </div>`;
    }

    contentEl.innerHTML = html;
    instance.show();
  }

  okBtn?.addEventListener('click', () => {
    //window.location.href = '/';
    // Disable pushed Jira issues
    instance.hide();
  });

  return { show };
})();

// --- Event Handlers (wired on DOMContentLoaded) ---
document.addEventListener('DOMContentLoaded', () => {
  // Wire the Run Iteration button
  const runBtn = document.getElementById('runIteration');
  runBtn?.addEventListener('click', async () => {
    runBtn.disabled = true;
//    showLoadingModal();
    try {
      await handleNextIteration();
    } catch (err) {
      console.error(err);
      alert('There was an error running the iteration.');
    } finally {
      runBtn.disabled = false;
//      hideLoadingModal();
    }
  });
});

document.addEventListener('DOMContentLoaded', () => {
  // Wire the Save Iteration button
  const runBtn = document.getElementById('saveIteration');
  runBtn?.addEventListener('click', async () => {
    runBtn.disabled = true;
    try {
      // Call with isSaveIteration
      await handleNextIteration(true);
    }
    catch (err) {
      console.error(err);
      alert('There was an error saving the iteration.');
    }
    finally {
      runBtn.disabled = false;
    }
  });
});

  // Handle modal close/cancel - delete pending iteration file
  document.getElementById('consolidationModal')?.addEventListener('hidden.bs.modal', () => {
    ConsolidationModal.deletePendingFile();
  });

  // Wire the Confirm & Push button
  const submitAllBtn = document.getElementById('submitAll');
  submitAllBtn?.addEventListener('click', async () => {

    if (submitAllBtn.dataset.busy === 'true') return;
    
    const hasApproved = Object.values(results || {}).some(arr => 
      Array.isArray(arr) && arr.some(r => r.status === 'approved')
    );
    
    if (!hasApproved) {
      alert('Please confirm at least one question (click "Yes") before submitting.');
      return;
    }
    
    submitAllBtn.disabled = true;
    submitAllBtn.dataset.busy = 'true';
    
    const iteration_information = window.pageData.iteration_information || {};
    const userText = (document.getElementById('k-user')?.textContent || '—').replace(/^\s*User:\s*/,'').trim();
    const question_number = window.pageData.questionCount || 0;
    const issue_number = (iteration_information["total_issue_count"] || 0) - (iteration_information["orphan_count"] || 0);
    
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
    
    try {
      showLoadingModal();
      
      const saveRes = await fetch('/confirmation_completed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          results,
          meta: {
            totalApproved,
            questionIssueCount: issue_number,
            userName: userText,
            qNumber: question_number,
            iterationInformation: iteration_information,
            project: globalParams.project || window.pageData?.project || '',
            outputFolder: globalParams.output_folder || '',
            isPushToJira: true
          }
        })
      });
      
      hideLoadingModal();
      
      const saveData = await saveRes.json().catch(() => ({}));
      
      if (!saveRes.ok) {
        alert('Failed to save confirmations: ' + (saveData.error || 'Unknown error'));
        return;
      }
      
      if (saveData.iteration_filename) {
        ConsolidationModal.setPendingFile(saveData.iteration_filename);
      }
      
      await ConsolidationModal.show();

      //
      
    } catch (err) {
      hideLoadingModal();
      console.error('Error saving confirmations:', err);
      alert('Error saving confirmations: ' + err.message);
    } finally {
      submitAllBtn.disabled = false;
      submitAllBtn.dataset.busy = '';
    }
  });

  // Submit button in modal - push to Jira
  document.getElementById('consolidationSubmitBtn')?.addEventListener('click', async () => {
    const btn = document.getElementById('consolidationSubmitBtn');
    const originalText = btn.innerHTML;
    
    try {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Pushing...';
      
      const filename = document.getElementById('consolidationFilename')?.textContent || '';
      
      const res = await fetch('/push_to_jira', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename })
      });
      
      const data = await res.json();

      // Disable sent items li.
      data.successful_items.forEach((item) => {
        const liElt = $(`#${item.question_id}`).find('li').has(`[data-issue^="${item.issuekey}_"]`);
        if (liElt.length) {
          liElt.addClass('disabled').css('opacity', '0.5');
        }
        else {
          console.error("Element liElt was not found.")
        }
      });

      
      if (!res.ok) {
        alert('Error: ' + (data.error || 'Failed to push to Jira'));
        return;
      }
      
      ConsolidationModal.markPushSucceeded();
      ConsolidationModal.hide();
      PushSummaryModal.show(data);
      
    } catch (err) {
      console.error('Push to Jira error:', err);
      alert('Network error: Could not reach the server');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalText;
      // TODO: save
      console.log(`TODO: save once pushed ...`);
      $("#saveIteration").click();
    }
  });
