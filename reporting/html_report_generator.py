# reporting/html_report_generator.py
"""HTML report generation from CSV and JSON data."""


def generate_html_from_csv(csv_path: str, output_html_path: str, title: str = "Inference Results"):
    import pandas as pd

    df = pd.read_csv(csv_path, na_filter=False).fillna('')
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link rel="stylesheet" href="{{{{ url_for('static', filename='bootstrap/css/bootstrap.min.css') }}}}">
    <style>
        body {{
            background-color: #f8f9fa;
        }}
        .table-container {{
            max-height: 600px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
        }}
        table {{
            margin-bottom: 0;
        }}
        thead th {{
            position: sticky;
            top: 0;
            z-index: 10;
            background-color: #cfe2ff; /* mismo color que .table-primary */
        }}
        .table th, .table td {{
            vertical-align: middle;
            text-align: center;
        }}
    </style>
</head>
<body class="py-4">
    <div class="container">
        <h1 class="mb-4 text-primary text-center">{title}</h1>
        <div class="table-responsive table-container bg-white rounded shadow-sm p-3">
            <table class="table table-striped table-hover table-bordered align-middle">
                <thead class="table-primary">
                    <tr>{"".join(f"<th>{col}</th>" for col in df.columns)}</tr>
                </thead>
                <tbody>
                    {"".join("<tr>" + "".join(f"<td>{val}</td>" for val in row) + "</tr>" for row in df.values)}
                </tbody>
            </table>
        </div>
        <div class="mt-4 text-center">
            <a href="/" class="btn btn-secondary">Home</a>
        </div>
    </div>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_html_path

def generate_html_from_json(json_folder: str, output_html_path: str, project, title, targets):
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{project} {title}</title>
    <link rel="stylesheet" href="/static/bootstrap/css/bootstrap.min.css"></link>
	<link rel="stylesheet" href="/static/dataTables/css/dataTables-2.3.2.css"></link>
	<script type="text/javascript" src="/static/jquery/js/jquery-3.7.1.js"></script>
	<script type="text/javascript" src="/static/dataTables/js/dataTables-2.3.2.js"></script>
</head>

<script>
$( document ).ready(function() {{

    // Setup - add a text input to each footer cell
    $('#example thead th').each(function (i) {{
        var title = $('#example thead th').eq($(this).index()).text();
		if(title != ""){{
			$(this).html(
				'<input type="text" placeholder="' + title + '" data-index="' + i + '" />'
			);
			}}
    }});

    let table = new DataTable('#example', {{footerCallback: myFooterCallback, ajax: '/data/{json_folder}?project={project}'}});

    // Filter event handler
    $(table.table().container()).on('keyup_', 'thead input', function () {{
        table
            .column($(this).data('index'))
            .search(this.value)
            .draw();
    }});

	 // Filter event handler (range option: < and > ops)
    $(table.table().container()).on('keyup', 'thead input', function () {{
		//table.column($(this).data('index')).search(this.value).draw();		
		var filterVal =  this.value.trim();
		console.log("filterVal: " + filterVal);
		var isLower = this.value.trim().startsWith("<") &&  this.value.trim().length > 1;
		var isHigher = filterVal.startsWith(">") &&  filterVal.length > 1;
		table.column($(this).data('index')).search.fixed('range', function (searchStr, data, index) {{
			if(isLower){{
				var isLowerOrEq = filterVal.includes("<=");
				var maxVal = isLowerOrEq ? parseFloat(filterVal.split("<=")[1]) : parseFloat(filterVal.split("<")[1]);
				return isLowerOrEq ? parseFloat(searchStr) <= maxVal : parseFloat(searchStr) < maxVal;
			}}
			else if(isHigher){{
				var isHigherOrEq = filterVal.includes(">=");
				var maxVal = isHigherOrEq ? parseFloat(filterVal.split(">=")[1]): parseFloat(filterVal.split(">")[1]);
				return isHigherOrEq ? parseFloat(searchStr) >= maxVal : parseFloat(searchStr) > maxVal;
			}}
			else{{
				return (searchStr.includes(filterVal));
			}}
		}}).draw();	
    }});

    // Highlight active filters
	$("thead th input, .dt-input").on('keyup', function(e) {{
		const bgCass = "bg-warning";
		var elt = $(e.target);
		if(elt.val() == ""){{
			elt.removeClass(bgCass);
			return;
		}}
		if(!elt.hasClass(bgCass)){{
			elt.addClass(bgCass);
		}}
	}});

}});

function myFooterCallback(row, data, start, end, display) {{
    let api = this.api();
    let targetColumn = 4;
    // Remove the formatting to get integer data for summation
    let intVal = function (i) {{
        return typeof i === 'string' ? i.replace(/[\$,]/g, '') * 1 : typeof i === 'number' ? i : 0;
    }};
    // Total over all pages
    total = api.column(targetColumn).data().reduce((a, b) => intVal(a) + intVal(b), 0);
    // Total over this page
    pageTotal = api.column(targetColumn, {{ page: 'all', filter: 'applied' }}).data().reduce((a, b) => intVal(a) + intVal(b), 0);		
    // Calculate the average
    var rowNumber = api.column(targetColumn, {{page: 'all', filter: 'applied'}}).data().length;
    var average = pageTotal > 0 ? (pageTotal / rowNumber) : 0;
    // Update footer
    api.column(targetColumn).footer().innerHTML = "Average: " + (average.toFixed(2));
}}
</script>

<body class="py-4">
    <div class="container">
        <h1 class="mb-4 text-primary text-center">
            <span>{project} {title}</span><br>
            <span><h5>Targets: {targets}</h5></span>
        </h1><hr>
        <!--h5 class="mb-4 text-primary text-center">Targets: {targets}</h5-->


		<table id="example" class="display">
			<thead>
				<tr>
                <th>Key</th>
                <th>Summary</th>
                <th>Field</th>
                <th>Prediction</th>
                <th>Confidence</th>
				</tr>
			</thead>
			<tfoot>
				<tr>
					<th colspan="4" style="text-align:left"></th>
					<th></th>
				</tr>
			</tfoot>
		</table>	
        <div class="mt-4 text-center">
            <a href="/" class="btn btn-secondary">Home</a>
            <a href="/confirmation" class="btn btn-secondary">Confirmation Questions</a>
        </div>
    </div>
</body>
</html>
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_html_path

def generate_audit_report_from_json(json_folder: str, output_html_path: str, project, title="Jira Field Audit Report"):
    html_content = f"""{{% extends "base.html" %}}

{{% block head_extra %}}
    <link rel="stylesheet" href="/static/dataTables/css/dataTables-2.3.2.css">
    <link rel="stylesheet" href="/static/dataTables/css/select.dataTables-3.0.1.css">
    <link rel="stylesheet" href="/static/highcharts/css/highcharts.css">
    <script type="text/javascript" src="/static/dataTables/js/dataTables-2.3.2.js"></script>
    <script type="text/javascript" src="/static/dataTables/js/dataTables.select-3.0.1.js"></script>
    <script type="text/javascript" src="/static/dataTables/js/select.dataTables-3.0.1.js"></script>
    <script type="text/javascript" src="/static/dataTables/js/sum()-2.3.2.js"></script>
    <script type="text/javascript" src="/static/highcharts/js/highcharts.js"></script>
    <style>
        /* DataTables JFIP overrides */
        table.dataTable thead th {{
            background: var(--navy) !important;
            color: #fff !important;
            font-weight: 600;
            border: none !important;
            padding: 0.75rem 1rem !important;
            white-space: nowrap;
        }}
        table.dataTable tbody td {{
            padding: 0.65rem 1rem !important;
            vertical-align: middle;
            border-color: var(--ink-200) !important;
        }}
        table.dataTable tbody tr:hover {{
            background: var(--info-light) !important;
        }}
        table.dataTable thead th input {{
            width: 100%;
            border: 1.5px solid rgba(255,255,255,0.3);
            border-radius: var(--radius-sm);
            padding: 0.3rem 0.6rem;
            font-size: 0.85rem;
            margin-top: 0.4rem;
            transition: all var(--transition-fast);
            background: rgba(255,255,255,0.12);
            color: #fff;
        }}
        table.dataTable thead th input::placeholder {{
            color: rgba(255,255,255,0.55);
        }}
        table.dataTable thead th input:focus {{
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(245,176,65,0.25);
            outline: none;
            background: rgba(255,255,255,0.22);
        }}
        table.dataTable thead th input.bg-warning {{
            background: var(--accent) !important;
            color: var(--navy) !important;
        }}
        .dt-container .dt-search input {{
            border: 1.5px solid var(--ink-200) !important;
            border-radius: var(--radius-sm) !important;
            padding: 0.5rem 0.8rem !important;
            transition: all var(--transition-fast);
        }}
        .dt-container .dt-search input:focus {{
            border-color: var(--primary) !important;
            box-shadow: var(--shadow-glow) !important;
        }}
        .dt-container .dt-info {{
            color: var(--ink-500);
            font-weight: 500;
        }}
        .dt-container .dt-paging button {{
            border-radius: var(--radius-sm) !important;
            font-weight: 600;
            transition: all var(--transition-fast);
        }}
        .dt-container .dt-paging button.current {{
            background: var(--primary) !important;
            border-color: var(--primary) !important;
            color: #fff !important;
        }}
        td.dt-control {{
            cursor: pointer;
            color: var(--primary);
            font-weight: 600;
        }}
        td.dt-control:hover {{
            color: var(--primary-dark);
        }}
        /* Highcharts JFIP theme */
        .highcharts-color-0 {{ fill: var(--primary); stroke: var(--primary); }}
        .highcharts-color-1 {{ fill: var(--accent); stroke: var(--accent); }}
        .highcharts-color-2 {{ fill: var(--success); stroke: var(--success); }}
        .highcharts-color-3 {{ fill: var(--navy); stroke: var(--navy); }}
        .highcharts-color-4 {{ fill: var(--primary-light); stroke: var(--primary-light); }}
        .highcharts-color-5 {{ fill: var(--danger); stroke: var(--danger); }}
        .highcharts-color-6 {{ fill: var(--accent-dark); stroke: var(--accent-dark); }}
        .highcharts-color-7 {{ fill: var(--navy-light); stroke: var(--navy-light); }}
        .highcharts-color-8 {{ fill: var(--ink-500); stroke: var(--ink-500); }}
        .highcharts-color-9 {{ fill: #8e44ad; stroke: #8e44ad; }}
        .highcharts-title {{
            fill: var(--navy) !important;
            font-family: var(--font-main) !important;
            font-weight: 700 !important;
            font-size: 1.1rem !important;
        }}
        .highcharts-background {{ fill: transparent !important; }}
        .highcharts-tooltip-box {{ fill: var(--card); stroke: var(--card-border); }}
        .highcharts-label text {{ fill: var(--ink-700) !important; font-family: var(--font-main) !important; }}
    </style>
{{% endblock %}}

{{% block content %}}
<div class="container" style="max-width: 1200px;">

    <!-- Page Header -->
    <div class="page-header d-flex align-items-center justify-content-between animate-fade-in">
        <div>
            <h1><i class="bi bi-clipboard-data me-2" style="color:var(--primary);"></i>{project} {title}</h1>
            <p class="subtitle mb-0">Field population analysis across project issues</p>
        </div>
        <a href="/field_completion" class="btn btn-outline-secondary">
            <i class="bi bi-arrow-left me-1"></i>Back
        </a>
    </div>

    <!-- Chart Section -->
    <div class="jfip-card animate-slide-up mb-4">
        <div id="demo-output" class="chart-display"></div>
    </div>

    <!-- Table Section -->
    <div class="jfip-card-flat animate-slide-up">
        <table id="example" class="display" style="width:100%;">
            <thead>
                <tr>
                    <th>Field</th>
                    <th>Completed</th>
                    <th>Total</th>
                    <th>Completion %</th>
                    <th>Initially Completed</th>
                    <th>Delta %</th>
                </tr>
            </thead>
        </table>
    </div>

</div>
{{% endblock %}}

{{% block scripts_extra %}}
<script>
$(document).ready(function() {{

    // Setup - add a text input to each header cell
    $('#example thead th').each(function (i) {{
        var title = $('#example thead th').eq($(this).index()).text();
        if(title != ""){{
            $(this).html(
                '<input type="text" placeholder="' + title + '" data-index="' + i + '" />'
            );
        }}
    }});

    let table = new DataTable('#example', {{
        ajax: '/audit/{json_folder}?project={project}',
        columns: [
            {{ className: 'dt-control', data: 'field' }},
            {{ data: 'completed' }},
            {{ data: 'total' }},
            {{ data: '%' }},
            {{ data: 'completed_before' }},
            {{ data: '%_delta' }}
        ],
    }});

    // Add event listener for opening and closing details
    table.on('click', 'td.dt-control', function (e) {{
        let tr = e.target.closest('tr');
        let row = table.row(tr);
        if (row.child.isShown()) {{
            row.child.hide();
        }}
        else {{
            row.child(format(row.data())).show();
        }}
    }});

    // Filter event handler
    $(table.table().container()).on('keyup_', 'thead input', function () {{
        table
            .column($(this).data('index'))
            .search(this.value)
            .draw();
    }});

    // Filter event handler (range option: < and > ops)
    $(table.table().container()).on('keyup', 'thead input', function () {{
        var filterVal = this.value.trim();
        var isLower = filterVal.startsWith("<") && filterVal.length > 1;
        var isHigher = filterVal.startsWith(">") && filterVal.length > 1;
        table.column($(this).data('index')).search.fixed('range', function (searchStr, data, index) {{
            if(isLower){{
                var isLowerOrEq = filterVal.includes("<=");
                var maxVal = isLowerOrEq ? parseFloat(filterVal.split("<=")[1]) : parseFloat(filterVal.split("<")[1]);
                return isLowerOrEq ? parseFloat(searchStr) <= maxVal : parseFloat(searchStr) < maxVal;
            }}
            else if(isHigher){{
                var isHigherOrEq = filterVal.includes(">=");
                var maxVal = isHigherOrEq ? parseFloat(filterVal.split(">=")[1]): parseFloat(filterVal.split(">")[1]);
                return isHigherOrEq ? parseFloat(searchStr) >= maxVal : parseFloat(searchStr) > maxVal;
            }}
            else{{
                return (searchStr.includes(filterVal));
            }}
        }}).draw();
    }});

    // Highlight active filters
    $("thead th input, .dt-input").on('keyup', function(e) {{
        const bgClass = "bg-warning";
        var elt = $(e.target);
        if(elt.val() == ""){{
            elt.removeClass(bgClass);
            return;
        }}
        if(!elt.hasClass(bgClass)){{
            elt.addClass(bgClass);
        }}
    }});

    // Create chart
    const chart = Highcharts.chart('demo-output', {{
        chart: {{
            type: 'pie',
            styledMode: true
        }},
        title: {{
            text: 'Completion Per Field'
        }},
        series: [
            {{
                data: chartData(table)
            }}
        ]
    }});

    // On each draw, update the data in the chart
    table.on('draw', function () {{
        chart.series[0].setData(chartData(table));
    }});

    function chartData(table) {{
        var counts = {{}};
        var rowIndex = 0;

        table
            .column(0, {{ search: 'applied' }})
            .data()
            .each(function (val) {{
                var completedVal = table.column(1, {{ search: 'applied' }}).data().toArray()[rowIndex];
                var totalVal = table.column(3, {{ search: 'applied' }}).data().toArray()[rowIndex];
                // Exclude completed fields.
                if(completedVal != totalVal)
                {{
                    counts[val] = completedVal;
                }}
                rowIndex++;
            }});

        return Object.entries(counts).map((e) => ({{
            name: e[0],
            y: e[1]
        }}));
    }}
}});

function format(d) {{
    var value = `Common "${{d.field}}" values:<br>`;
    d.values.forEach((val, index) => {{
        value += val.replace(/</g,'&lt;').replace(/>/g,'&gt;') + "<br>";
    }});
    return value;
}}
</script>
{{% endblock %}}
"""
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_html_path
