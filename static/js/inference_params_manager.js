  let disabledFields = [];
  let accuracyPerField = {};

  function updateSubmitBtnState() {
    const checkedBoxes = $('.fieldGrid:checked');
    const unmutedCheckedBoxes = checkedBoxes.filter(function() {
        return !$(this).hasClass('text-muted');
    });
    $('#showJiraViewerBtn').prop('disabled', unmutedCheckedBoxes.length === 0);
    $('#runIterationBtn').prop('disabled', unmutedCheckedBoxes.length === 0);
  }

  function updateFieldBadges(selectedTypesPerField) {
    $(".badge.labeledDataPercent").html("");
    $(".badge.labeledDataPercent").removeClass("bg-warning bg-success");
    $(".badge.testDataPercent").html("");
    $(".badge.testDataPercent").removeClass("bg-warning bg-success");
    const projectKey = $('#filename').val().replace(".json", "");
    const infoDict = fieldMatrix[projectKey].inferable_fields_info;
    Object.entries(selectedTypesPerField).forEach(([fieldName, types]) => {
      const labeledCountPerIssueType = infoDict[fieldName].labeled_count_per_issue_type;
      const totalIssueCount = infoDict[fieldName].total_issues;
      const selectedLabeledCount = types.reduce((sum, key) => {
        return sum + (labeledCountPerIssueType[key] || 0);
      }, 0);
      const selectedLabeledPercent = 100 * selectedLabeledCount / totalIssueCount
      //console.log(`selectedLabeledPercent: ${selectedLabeledPercent.toFixed(2)}`);
      const minLabeledPercent = $('#labeledDataRatio').val();
      const minTestDataSize = $('#minTestDataSize').val();
      $(`#${fieldName}-badge`).html(`${selectedLabeledPercent.toFixed(2)}%`);
      $(`#${fieldName}-tBadge`).html(Math.trunc(selectedLabeledCount / 5));
      const badgeColor = selectedLabeledPercent < minLabeledPercent ? "bg-warning" : "bg-success";
      const tBadgeColor = selectedLabeledCount < 5 * minTestDataSize ? "bg-warning" : "bg-success";
      $(`#${fieldName}-badge`).addClass(badgeColor);
      $(`#${fieldName}-tBadge`).addClass(tBadgeColor);
    });
  }

  function setFieldGrid() {
    let gridDict = {};
    const checkedBoxes = $('.fieldGrid:checked');
    checkedBoxes.map(function() {
        const name = $(this).attr('name')
        const fieldName = name.split(':')[0];
        const issueType = name.split(':')[1];
        if (!gridDict.hasOwnProperty(fieldName)) {
            gridDict[fieldName] = [];
        }
        if (!gridDict[fieldName].includes(issueType)) {
            gridDict[fieldName].push(issueType);
        }

    });
    updateFieldBadges(gridDict);

    const fieldGridDict = {"data": gridDict, "metadata": disabledFields, "accuracyPerField": accuracyPerField};
    updateSubmitBtnState();

    const form = document.getElementById('formId');
    const formData = new FormData(form);
    document.querySelector('#hiddenFieldId')?.remove();
    const hiddenField = document.createElement('input');
    hiddenField.id = 'hiddenFieldId';
    hiddenField.type = 'hidden';
    hiddenField.name = 'fieldGridDict';
    hiddenField.value = JSON.stringify(fieldGridDict);
    form.appendChild(hiddenField);
  }

  function addFieldGrid(element) {
    let isSubmitEnabled = false;
    const projectName = element.value;
    const projectKey = projectName.replace(".json", "");
    if(projectKey === "") {
        document.getElementById('fieldMatrixLabel').innerHTML = "";
        document.getElementById('fieldMatrix').innerHTML = "";
        return;
    }

    const labeledDataRatio = $('#labeledDataRatio').val();
    const minTestDataSize = $('#minTestDataSize').val();
    const fieldInfo = fieldMatrix[projectKey]["inferable_fields_info"]
    inferableFields = fieldMatrix[projectKey]["inferable_fields"];
    issueTypes = fieldMatrix[projectKey]["issue_types"];
    let thStr = "<thead><tr><th>Field</th>";
    issueTypes.forEach((item) => { thStr += `<th>${item}</th>`; });
    thStr += "</tr></thead>";
    tbStr = "<tbody>";
    inferableFields.forEach((field) => {
      let badgeTooltip = `data-bs-toggle="tooltip" title="Labeled Data %"`;
      let badgeClasses = "badge bg-warning me-2 float-end labeledDataPercent";
      let badgeSpan = `<span class="${badgeClasses}" id="${field}-badge" ${badgeTooltip}></span>`;
      let tBadgeTooltip = `data-bs-toggle="tooltip" title="Test Data Size"`;
      let tBadgeClasses = "badge bg-warning me-2 float-end testDataSize";
      let tBadgeSpan = `<span class="${badgeClasses}" id="${field}-tBadge" ${tBadgeTooltip}></span>`;
      let field_wrapper = `<span id="${field}-tooltip" name="${field}" data-bs-toggle="tooltip" data-bs-placement="left">`;
      field_wrapper += `${field}</span>`
      tbStr += `<tr id="${projectKey} ${field}"><td>${field_wrapper} ${badgeSpan} ${tBadgeSpan}</td>`;

      issueTypes.forEach((issueType) => {
        let isChecked = Object.hasOwn(latestFieldMatrix, projectKey)
        isChecked =  isChecked && Object.hasOwn(latestFieldMatrix[projectKey], field)
        isChecked = isChecked && latestFieldMatrix[projectKey][field].includes(issueType);
        isSubmitEnabled = isSubmitEnabled || isChecked;
        const checkedStr = isChecked ? "checked" : "";
        const checkBoxStr = `
          <div class="form-check">
            <input type="checkbox" class="form-check-input fieldGrid" name="${field}:${issueType}" onchange="setFieldGrid()" ${checkedStr}>
          </div>
        `;
        tbStr += `<td>${checkBoxStr}</td>`;
      });
      tbStr += "</tr>";
    });
    tbStr += "</tbody>"

    const labelHtml = `<i class="bi bi-ui-checks-grid me-1"></i>Select Target Fields`
    matrixHtml = `<div class="container"><table id="grid" class="table table-striped">${thStr}${tbStr}</table></div>`;
    document.getElementById('fieldMatrixLabel').innerHTML = labelHtml;
    document.getElementById('fieldMatrix').innerHTML = matrixHtml;
    if(isSubmitEnabled) { setFieldGrid(); }
    updateFieldGrid();
    updateDropdowns(projectKey);
    updateSubmitBtnState();
    initializeTooltips(projectKey);
  }

  function updateFieldGrid() {
    disabledFields = [];
    const labeledDataRatioThreshold = Number($('#labeledDataRatio').val());
    const minTestDataSize = Number($('#minTestDataSize').val());

    $('#grid tbody tr').each(function() {
        const $row = $(this);
        const projectKey = $(this).attr("id").split(' ')[0];
        const field = $(this).attr("id").split(' ')[1];
        const fieldInfo = fieldMatrix[projectKey].inferable_fields_info[field];
        const labeledDataRatio = Number(fieldInfo["labeled_percentage"]);
        const testDataSize = Number(fieldInfo["test_data_size"]);
        if(labeledDataRatio < labeledDataRatioThreshold || testDataSize < minTestDataSize){
          $(this).find("input").addClass("text-muted opacity-25").css("pointer-events", "none");
          disabledFields.push(field);
        }
        else {
          $(this).find("input").removeClass("text-muted opacity-25").css("pointer-events", "");
        }
    });
    disabledNativelyImpossibleLinks();
    setFieldGrid();
  }

  function disabledNativelyImpossibleLinks() {
    const impossibleLinks = ["epic_link:Epic", "epic_link:Sub-task"];
    impossibleLinks.forEach(impossibleLink => {
      $(`input[name="${impossibleLink}"]`).addClass("text-muted opacity-25").css("pointer-events", "none");
    });
  }

  function updateDropdowns(projectKey) {
    const projectParams = savedParams[projectKey] ?? {};
    const minTestDataSize = projectParams.min_test_data_size;
    const labeledDataRatio = projectParams.acceptable_labeled_data_ratio;
    if(labeledDataRatio != null){ $('#labeledDataRatio').val(labeledDataRatio).trigger('change'); }
    if(minTestDataSize != null){ $('#minTestDataSize').val(minTestDataSize).trigger('change'); }
  }

  function updateFieldAccuracy(element) {
    const projectKey = element.id.split('-')[0];
    const field = element.id.split('-')[1];
    const accuracy = Number(element.value);
    accuracyPerField[projectKey] ??= {};
    accuracyPerField[projectKey][field] = accuracy;
    setFieldGrid();
  }

function initializeTooltips(projectKey){
  const toggles = document.querySelectorAll('[data-bs-placement="left"]');
  toggles.forEach(element => {
    const field = element.getAttribute('name');
    const infoDictPerProject = bestPerformancePerProject[projectKey] ?? {};
    let infoDictPerProject2 = fieldMatrix[projectKey] ?? {};
    infoDictPerProject2 = infoDictPerProject2["inferable_fields_info"] ?? {};
    const testDataSize = infoDictPerProject2[field]["test_data_size"];
    const infoDict = infoDictPerProject[field];
    let tooltipDesc
    if(infoDict != null){
        const mlMode = infoDict.ml_model;
        let optimalConfidence = (100 * infoDict.optimal_confidence).toFixed(2);
        optimalConfidence = infoDict.optimal_confidence == 1 ? "100" : optimalConfidence;
        let f1Score = (100 * infoDict.optimal_confidence_f1_score).toFixed(2);
        f1Score = infoDict.optimal_confidence_f1_score == 1 ? "100" : f1Score;
        tooltipDesc = `ML Model: ${mlMode}, Optimal Confidence: ${optimalConfidence}%, Estimated F1-Score: ${f1Score}%`;
        tooltipDesc += `, Test Data Size: ${testDataSize}`;
    }
    else {
        tooltipDesc = `ML Model: ---, Optimal Confidence: ---, Estimated F1-Score: ---, Test Data Size: ${testDataSize}`;
    }
    const toolTip = document.getElementById(element.id);
    const tooltipDescHtml = tooltipDesc.replaceAll(", ", "<br>")
    toolTip.setAttribute('data-bs-html', true)
    toolTip.setAttribute('data-bs-title', `<div class="text-start">${tooltipDescHtml}</div>`);
    const tabTooltip = new bootstrap.Tooltip(toolTip, { trigger: 'hover' });
  });
}

async function setParamsAndRunInferenceIteration() {
    const myForm = document.querySelector('#formId');
    const formData = new FormData(myForm);
    const formObject = Object.fromEntries(formData.entries());
    const url = '/save_grid_parameters';
    try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(formObject)
        });
        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        // Quick fix: create a dummy link and click it
        showGenericModal("Inference Iteration", "/get_iteration_progress", 2.5, "/abort_iteration");
        const tempLink = document.createElement('a');
        tempLink.href = `/run_inference_iteration?db=${data.project_json}`;
        tempLink.click();
    } catch (error) {
        console.error('Network or Parsing Error:', error);
    }
}
