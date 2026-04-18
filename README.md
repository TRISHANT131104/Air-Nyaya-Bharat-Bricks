<h1 align="center">✈️ Air-Nyaya</h1>

<p align="center">
AI-powered flight disruption monitoring & passenger entitlement assistant based on DGCA CAR regulations.
</p>

<hr>

<h2>📌 What Air-Nyaya Does</h2>

<p>
Air-Nyaya proactively monitors flight delays, determines passenger entitlements under DGCA regulations,
and guides users through structured grievance escalation via airlines, AirSewa, and the National Consumer Helpline (NCH).
</p>

<hr>

<h2>🏗️ Architecture Diagram</h2>

<p align="center">
<img src="https://drive.google.com/file/d/1GkSTexP9RgAN-TeV2LKiIh1QV1gK2PMp/view?usp=sharing" width="700">
</p>

<hr>

<h2>⚙️ System Architecture Overview</h2>

<ul>
<li><b>Bronze Layer:</b> Raw DGCA CAR regulatory rules ingestion</li>
<li><b>Silver Layer:</b> Structured regulatory summaries and clause extraction</li>
<li><b>Gold Layer:</b> Rule graph construction with entitlement parameters</li>
<li><b>Classifier Engine:</b> Deterministic mapping of disruption scenarios to CAR clauses</li>
<li><b>Query Parser:</b> Extracts grievance metadata from user input</li>
<li><b>Decision Engine:</b> Identifies compensation eligibility</li>
<li><b>Action Engine:</b> Generates escalation workflow steps</li>
<li><b>Flight Monitor:</b> Tracks delay thresholds using Aviationstack API</li>
<li><b>Notification Engine:</b> Pushes entitlement update alerts</li>
</ul>

<hr>

<h2>🚀 Deployed Prototype</h2>

<p>
<a href="https://hello-world-7474654193956536.aws.databricksapps.com">
Open Air-Nyaya App
</a>
</p>

<hr>

<h2>🎬 Demo Video</h2>

<p>
<a href="https://drive.google.com/file/d/1ZIA4Le1c0wosxNgZYB_t_cbEHeazY__i/view?usp=drivesdk">
Watch Demo (2 minutes)
</a>
</p>

<hr>

<h2>📡 Proactive Flight Monitoring Engine</h2>

<p>
Air-Nyaya includes a background scheduler that checks flight status every hour and recalculates
entitlements whenever disruption thresholds are crossed.
</p>

<pre>
Scheduler Trigger Condition:

min(
    current_time − last_checked_time,
    current_time − departure_time
) ≥ 1 hour
</pre>

<p>
If eligibility changes, the system automatically triggers notifications for:
</p>

<ul>
<li>Meal vouchers</li>
<li>Lounge access</li>
<li>Alternate routing</li>
<li>Refund eligibility</li>
<li>Monetary compensation</li>
</ul>

<hr>

<h2>🧠 Databricks Technologies Used</h2>

<ul>
<li>Databricks Apps (deployment)</li>
<li>Databricks Notebooks</li>
<li>Delta Tables (flight tracking roster)</li>
<li>Scheduled Jobs (polling scheduler)</li>
<li>MLflow (experiment tracking)</li>
<li>Unity Catalog (rule governance)</li>
</ul>

<hr>

<h2>🧪 Open-Source Stack</h2>

<ul>
<li>Python</li>
<li>FastAPI</li>
<li>Pandas</li>
<li>Aviationstack API</li>
<li>Rule-based entitlement engine</li>
</ul>

<hr>

<h2>▶️ How to Run Locally</h2>

<pre>
git clone https://github.com/&lt;your-username&gt;/Air-Nyaya.git
cd Air-Nyaya
pip install -r requirements.txt
python app.py
python fetch_status.py
streamlit run main.py
</pre>

<hr>

<h2>🧭 Demo Steps</h2>

<ol>
<li>Open deployed application</li>
<li>Enter flight number</li>
<li>Select disruption scenario</li>
<li>Submit grievance query</li>
<li>View entitlement classification</li>
<li>Trigger escalation workflow</li>
<li>Observe alternate route suggestions</li>
<li>Simulate delay update → entitlement refresh</li>
</ol>

<hr>

<h2>🏛️ Regulatory Intelligence Backbone</h2>

<p>
Air-Nyaya converts DGCA CAR Section 3 Series M Part IV into executable rule graphs that enable
automatic entitlement detection and structured grievance escalation guidance.
</p>

<hr>

<h2>📁 Repository Structure</h2>

<pre>
Air-Nyaya/
│
├── app.py
├── fetch_status.py
├── rule_engine/
├── scheduler/
├── grievance_classifier/
├── datasets/
├── notebooks/
└── README.md
</pre>

<hr>

<h2>📝 Project Summary (Submission Description)</h2>

<p>
Air-Nyaya is an AI-powered passenger rights assistant that monitors flights in real time,
detects disruptions, computes DGCA CAR entitlements automatically, and guides users through
structured grievance escalation via airlines, AirSewa, and the National Consumer Helpline.
</p>
