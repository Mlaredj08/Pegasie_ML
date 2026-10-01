// Put validateIssueTypes in outer scope so both handlers can use it
function validateIssueTypes(showFeedback = true) {
  const alertBox = document.getElementById("issuetypeAlert");
  const issueTypeBox = document.getElementById("issuetypeBox");
  const issueTypeCheckboxes = document.querySelectorAll(".group-issuetype");
  const ok = Array.from(issueTypeCheckboxes).some(cb => cb.checked);

  if (!ok && showFeedback) {
    alertBox.classList.remove("d-none");
    issueTypeBox.classList.add("border", "border-danger", "rounded");
    issueTypeBox.scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    alertBox.classList.add("d-none");
    issueTypeBox.classList.remove("border", "border-danger", "rounded");
  }
  return ok;
}

// Handle "Select All" checkboxes
document.querySelectorAll(".select-all").forEach(selectAllCheckbox => {
  selectAllCheckbox.addEventListener("change", function () {
    const group = this.dataset.group;
    const checkboxes = document.querySelectorAll(`.group-${group}`);
    checkboxes.forEach(cb => cb.checked = this.checked);
    // ✅ Re-validate after bulk toggle
    if (group === "issuetype") validateIssueTypes(false);
  });
});

// Validate on form submit and use async export with progress modal
const generateForm = document.getElementById("generateForm");
if (generateForm) {
  generateForm.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!validateIssueTypes(true)) return;

    const formData = new FormData(generateForm);
    const actionUrl = generateForm.getAttribute("action");

    const btnCancel = document.getElementById("btnCancelExport");

    // Reset modal state
    document.getElementById("exportMsg").textContent = "Starting export...";
    document.getElementById("exportBar").style.width = "0%";
    document.getElementById("exportBar").textContent = "0%";
    document.getElementById("exportPhase").textContent = "";
    document.getElementById("exportError").classList.add("d-none");
    document.getElementById("exportCancelledMsg").classList.add("d-none");
    document.getElementById("exportSpinner").style.display = "";
    btnCancel.disabled = false;
    btnCancel.textContent = "";
    btnCancel.innerHTML = '<i class="bi bi-x-lg me-1"></i>Cancel Export';

    // Show progress modal
    const modal = new bootstrap.Modal(document.getElementById("exportProgressModal"));
    modal.show();

    function _finaliseModal() {
      btnCancel.disabled = true;
      btnCancel.innerHTML = '<i class="bi bi-x-lg me-1"></i>Cancel Export';
    }

    // Submit via AJAX
    fetch(actionUrl, { method: "POST", body: formData })
      .then(res => res.json())
      .then(data => {
        if (!data.ok) {
          document.getElementById("exportError").textContent = "Failed to start export.";
          document.getElementById("exportError").classList.remove("d-none");
          document.getElementById("exportSpinner").style.display = "none";
          _finaliseModal();
          return;
        }
        // Start polling
        const pollId = setInterval(() => {
          fetch("/get_jira_export_progress")
            .then(r => r.json())
            .then(prog => {
              const pct = prog.total > 0 ? Math.min(100, Math.round((prog.fetched / prog.total) * 100)) : 0;
              document.getElementById("exportBar").style.width = pct + "%";
              document.getElementById("exportBar").textContent = pct + "%";
              document.getElementById("exportMsg").textContent = prog.message || "Processing...";

              const phaseLabel = prog.phase === "issues" ? "Fetching issues..." :
                                 prog.phase === "comments" ? "Fetching comments..." :
                                 prog.phase === "saving" ? "Saving file..." : "";
              document.getElementById("exportPhase").textContent = phaseLabel;

              if (prog.status === "done") {
                clearInterval(pollId);
                document.getElementById("exportBar").style.width = "100%";
                document.getElementById("exportBar").textContent = "100%";
                document.getElementById("exportSpinner").style.display = "none";
                document.getElementById("exportMsg").textContent =
                  prog.message + (prog.result_filename ? "\nFile: " + prog.result_filename : "");
                _finaliseModal();
                // Redirect home after a short delay
                setTimeout(() => { window.location.href = "/"; }, 2000);
              } else if (prog.status === "error") {
                clearInterval(pollId);
                document.getElementById("exportSpinner").style.display = "none";
                document.getElementById("exportError").textContent = prog.error || "Unknown error";
                document.getElementById("exportError").classList.remove("d-none");
                _finaliseModal();
              } else if (prog.status === "cancelled") {
                clearInterval(pollId);
                document.getElementById("exportSpinner").style.display = "none";
                document.getElementById("exportCancelledMsg").classList.remove("d-none");
                document.getElementById("exportMsg").textContent = "";
                document.getElementById("exportPhase").textContent = "";
                _finaliseModal();
                // Close modal after a short delay and return to the export page
                setTimeout(() => { modal.hide(); }, 2500);
              }
            })
            .catch(() => {});
        }, 1500);
      })
      .catch(err => {
        document.getElementById("exportError").textContent = "Network error: " + err.message;
        document.getElementById("exportError").classList.remove("d-none");
        document.getElementById("exportSpinner").style.display = "none";
        _finaliseModal();
      });
  });

  // Cancel button handler
  document.getElementById("btnCancelExport").addEventListener("click", function () {
    this.disabled = true;
    this.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span>Cancelling...';
    fetch("/cancel_jira_export", { method: "POST" })
      .catch(() => {});
  });
}

// Live validation on manual checkbox changes
document.addEventListener("change", function (e) {
  if (e.target && e.target.classList.contains("group-issuetype")) {
    validateIssueTypes(false);
        // 🔄 Update the select-all checkbox for this group
    const group = "issuetype"; // here we hardcode, but could also read from class
    const selectAllCheckbox = document.querySelector(`.select-all[data-group="${group}"]`);
    const allGroupCheckboxes = document.querySelectorAll(`.group-${group}`);
    const allChecked = Array.from(allGroupCheckboxes).every(cb => cb.checked);

    selectAllCheckbox.checked = allChecked;
  }
});
