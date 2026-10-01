// progress-modal.js
// Requires:
// - Bootstrap 5
// - jQuery

let progressInterval = null;

/**
 * Creates Bootstrap modal
 */
function createModal(
    title,
    waitMsg = "Your request is being processed, please wait ...",
    abortEndpoint = null,
    titleIcon = null
) {

    const titleIconHtml = titleIcon == null ? "" : `<i class="bi ${titleIcon} me-2" style="color:var(--accent);"></i>`;
    // Remove existing modal if already present
    $("#progressModal").remove();

    let abortBtn = `<hr><button id="abortBtn" type="button" class="btn btn-danger" disabled>Stop</button>`;
    abortBtn = abortEndpoint != null ? abortBtn : "";
    const modalHtml = `
        <div class="modal fade"
             id="progressModal"
             tabindex="-1"
             data-bs-backdrop="static"
             data-bs-keyboard="false">

            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">

                    <div class="modal-header">
                        <h5 class="modal-title">${titleIconHtml}${title}</h5>
                    </div>

                    <div class="modal-body">

                        <div id="description" class="mb-2 p-5__ bg-light__ border__"></div>

                        <div class="text-center mb-4">
                            <div class="spinner-border text-primary"
                                 role="status">
                            </div>

                            <div id="waitMsg" class="mt-2">
                                ${waitMsg}
                            </div>
                        </div>

                        <div id="progressContainer"></div>
                        <div class="text-end">${abortBtn}</div>

                    </div>

                </div>
            </div>
        </div>
    `;

    $("body").append(modalHtml);
    $("#abortBtn").on("click", function() {
        abortIteration($('#abortBtn'), abortEndpoint);
    });
}

/**
 * Fetch progress data from server
 */
async function getProgress(endpoint = "/getProgressStatus") {

    try {

        const response = await $.ajax({
            url: endpoint,
            method: "GET",
            dataType: "json"
        });

        return response;

    } catch (error) {

        console.error("Error fetching progress:", error);
        return null;
    }
}

/**
 * Dynamically adds progress bars
 */
function addProgress(progressData_) {
    const progressData = progressData_.progressbars
    const container = $("#progressContainer");
    const descriptionDiv = $("#description");

    // Add description if any
    const textDescription = progressData_.text_description ?? null;
    const htmlDescription = progressData_.html_description ?? null;
    const description = htmlDescription != null ? htmlDescription : textDescription != null ? textDescription : "";
    if (descriptionDiv.html() != description) {
        descriptionDiv.html(description);
    }


    $.each(progressData, function(key, value) {

        // Skip if already exists
        if ($(`#progress-${key}`).length > 0) {
            return;
        }

        const progressHtml = `
            <div class="mb-2 progress-wrapper"
                 id="wrapper-${key}">

                <div class="d-flex justify-content-between mb-1__">
                    <span>${key}</span>
                    <span id="label-${key}">0%</span>
                </div>

                <div class="progress" style="height: 24px;">

                    <div id="progress-${key}"
                         class="progress-bar progress-bar-striped progress-bar-animated"
                         role="progressbar"
                         style="width: 0%;">

                        0%

                    </div>

                </div>
            </div>
        `;

        container.append(progressHtml);
    });
}

/**
 * Updates all progress bars
 */
async function updateProgress(endpoint) {

    const progressData_ = await getProgress(endpoint);
    const progressData = progressData_.progressbars;

    if (!progressData) {
        return;
    }

    // Add progress bars if missing
    addProgress(progressData_);

    // Update spinner wait message if needed
    new_wait_msg = progressData_.spinner_wait_message ?? null;
    active_processes = progressData_.active_processes ?? 0;
    is_abort = progressData_.is_abort ?? false;
    console.log(`is_abort: ${is_abort}`);
    console.log(`active_processes: ${active_processes}`);
    $("#abortBtn").prop('disabled', active_processes == 0);
    if (new_wait_msg  != null) {
        cur_wait_msg =  $('#waitMsg').text().trim();
        if (cur_wait_msg != new_wait_msg) {
            $("#waitMsg").text(new_wait_msg);
        }
    }


    let allDone = true;
    const isProgressBars = Object.keys(progressData).length !== 0;

    $.each(progressData, function(key, value) {

        const percent = Math.round(value.progress * 100);

        const progressBar = $(`#progress-${key}`);

        progressBar.css("width", `${percent}%`);
        progressBar.attr("aria-valuenow", percent);
        progressBar.text(`${percent}%`);

        //$(`#label-${key}`).text(`${percent}%`);
        const elapsed_hms = value["elapsed"] ?? "---";
        $(`#label-${key}`).text(`${elapsed_hms}`);

        // Mark complete
        if (percent >= 100) {
            progressBar
                .removeClass("progress-bar-animated")
                .removeClass("progress-bar-striped")
                .addClass("bg-success");

        } else {

            if (is_abort) {
                _percent = 100;
                progressBar.css("width", `${_percent}%`);
                progressBar.attr("aria-valuenow", _percent);
                progressBar.text(`${_percent}%`);
                progressBar
                    .removeClass("progress-bar-animated")
                    .removeClass("progress-bar-striped")
                    .addClass("bg-danger");
                allDone = true;
            }
            else {
                allDone = false;
            }
        }
    });

    // Auto close when everything reaches 100%
    if (isProgressBars && allDone) {

        clearInterval(progressInterval);

        setTimeout(() => {
            console.log(`[DEBUG] closing the modal ...`);
            closeModal();
        }, 5000);
    }
}

/**
 * Opens modal and starts polling
 */
function showGenericModal(
    title,
    endpoint,
    intervalInSec = 2,
    abortEndpoint = null,
    waitMsg = "Your request is being processed, please wait ...",
    titleIcon = "bi-cpu"
) {

    createModal(title, waitMsg, abortEndpoint, titleIcon);

    const modalElement = document.getElementById("progressModal");

    const modal = new bootstrap.Modal(modalElement);

    modal.show();

    // Immediate update
    updateProgress(endpoint);

    // Polling
    progressInterval = setInterval(() => {

        updateProgress(endpoint);

    }, intervalInSec * 1000);
}

/**
 * Closes modal
 */
function closeModal() {

    clearInterval(progressInterval);

    const modalElement = document.getElementById("progressModal");

    if (!modalElement) {
        return;
    }

    const modal =
        bootstrap.Modal.getInstance(modalElement);

    if (modal) {
        modal.hide();
    }

    // Remove modal after animation
    setTimeout(() => {
        $("#progressModal").remove();
    }, 500);
}

async function abortIteration(elt, abortEndpoint) {
    const response = await fetch(abortEndpoint, {
        method: "POST",
        headers: {
        "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }
    const data = await response.json();
    const killCount = data.kill_count || 0;
    $(elt).prop('disabled', killCount > 0);
    return data;
}