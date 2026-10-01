
document.addEventListener("DOMContentLoaded", () => {
    const selectElement = document.getElementById("filename");

    selectElement.addEventListener("change", () => {
        const selectedProject = selectElement.value;
        const list_match =  selectedProject.match(/^(\w+)_model_(\d{8}_\d{6})\.json$/);
        const project_name = `${list_match[1]}_${list_match[2]}`;

        fetch("/get_iterations_by_project", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project: project_name })
        })
            .then(res => res.json())
            .then(data => {
                var tableBody = document.querySelector("table tbody");
                if (!tableBody) {
                    // Create the table and append to DOM
                    const container = document.querySelector(".container");

                    const tableWrapper = document.createElement("div");
                    tableWrapper.className = "mt-5";

                    const heading = document.createElement("h3");
                    heading.className = "mb-3 text-primary";
                    heading.textContent = "Inference Iteration Summary";

                    const responsiveDiv = document.createElement("div");
                    responsiveDiv.className = "table-responsive";

                    table = document.createElement("table");
                    table.className = "table table-bordered table-striped iterations-table";

                    const thead = document.createElement("thead");
                    thead.className = "table-primary";
                    thead.innerHTML = `
                                    <tr>
                                    <th># Iteration</th>
                                    <th>Day/Time</th>
                                    <th># Questions</th>
                                    <th>User</th>
                                    <th>Field</th>
                                    <th>Predictions</th>
                                    <th>% Confidence</th>
                                    <th>Approved Predictions</th>
                                    <th>Cumulative Approved Predictions</th>
                                    <th>Pending Approval</th>
                                    <th>Cumulative Approval Rate</th>
                                    </tr>
                                `;

                    tableBody = document.createElement("tbody");

                    table.appendChild(thead);
                    table.appendChild(tableBody);
                    responsiveDiv.appendChild(table);
                    tableWrapper.appendChild(heading);
                    tableWrapper.appendChild(responsiveDiv);
                    container.appendChild(tableWrapper);
                } else {
                    tableBody = document.querySelector("tbody");
                    tableBody.innerHTML = ""; // Clear existing rows
                }

                const iterations = data.iterations || [];

                iterations.forEach(row => {
                    const tr = document.createElement("tr");

                    tr.innerHTML = `
                    <td>${row.iteration}</td>
                    <td>${row.time_stamp}</td>
                    <td>${row.questions_number}</td>
                    <td>${row.user}</td>
                    <td>${row.field}</td>
                    <td>${row.predictions}</td>
                    <td>${row.confidence}%</td>
                    <td>${row.approved}</td>
                    <td>${row.cumulative_approved}</td>
                    <td>${row.remaining}</td>
                    <td>${row.completion}%</td>
                    `;

                    tableBody.appendChild(tr);
                });
                if (data.totals) {
                    const totalRow = document.createElement("tr");
                    totalRow.className = "table-warning fw-bold"; // Optional styling

                    totalRow.innerHTML = `
                        <td colspan="2">Total</td>
                        <td>${data.totals.questions}</td>
                        <td></td>
                        <td>${data.totals.predictions}</td>
                        <td></td>
                        <td>${data.totals.approved}</td>
                        <td></td>
                        <td></td>
                        <td></td>
                    `;

                    tableBody.appendChild(totalRow);
                }

            })
            .catch(err => {
                console.error("Failed to fetch iterations:", err);
                alert("Error fetching iterations. See console for details.");
            });
    });
    selectElement.dispatchEvent(new Event("change"));
});

