---
name: python-data-analysis-automation
description: "Using Python to automate data collection, cleaning, analysis, and reporting"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - data
  - analytics
  - business-intelligence
  - data-analyst
---

SKILL: PYTHON DATA ANALYSIS & AUTOMATION

SKILL ID:       DA-SK-004
ROLE:           Data Analyst
CATEGORY:       Programming & Automation
DIFFICULTY:     Advanced
ESTIMATED TIME: Ongoing (core daily skill)

DESCRIPTION
Using Python to automate data collection, cleaning, analysis, and reporting
tasks that would be slow or impossible in spreadsheets. This covers the
pandas ecosystem, data wrangling, automated reporting, API integration, and
building reusable analytical pipelines.

STEP-BY-STEP PROCEDURE

STEP 1: SET UP THE ANALYTICAL ENVIRONMENT
  - Use virtual environments (venv or conda) for project isolation
  - Core libraries:
    * pandas: Data manipulation and analysis
    * numpy: Numerical computing
    * matplotlib + seaborn: Static visualisation
    * plotly: Interactive visualisation
    * scipy + statsmodels: Statistical analysis
    * scikit-learn: Machine learning (clustering, regression, classification)
    * openpyxl: Excel file reading/writing
    * requests: API data collection
    * sqlalchemy: Database connections
  - Use Jupyter Notebooks for exploratory analysis
  - Use .py scripts for production pipelines

STEP 2: DATA COLLECTION & INGESTION
  From databases:
    import sqlalchemy
    engine = sqlalchemy.create_engine('postgresql://user:pass@host/db')
    df = pd.read_sql('SELECT * FROM table WHERE date > ...', engine)

  From APIs:
    import requests
    response = requests.get('https://api.example.com/data', headers=auth)
    df = pd.json_normalize(response.json())

  From files:
    df = pd.read_csv('data.csv')
    df = pd.read_excel('report.xlsx', sheet_name='Sheet1')
    df = pd.read_json('data.json')

STEP 3: DATA CLEANING & TRANSFORMATION
  Common cleaning operations:
  - Handle missing values: df.dropna(), df.fillna(), df.interpolate()
  - Remove duplicates: df.drop_duplicates()
  - Fix data types: df['date'] = pd.to_datetime(df['date'])
  - Rename columns: df.rename(columns={'old': 'new'})
  - String cleaning: df['name'].str.strip().str.lower()
  - Outlier handling: IQR method or Z-score filtering
  - Merge datasets: pd.merge(df1, df2, on='key', how='left')
  - Pivot and reshape: df.pivot_table(), df.melt(), df.stack()
  - Create calculated columns: df['profit_margin'] = df['profit'] / df['revenue']

STEP 4: ANALYSIS PATTERNS
  Aggregation:
    df.groupby('category').agg({'revenue': 'sum', 'orders': 'count'})

  Time series:
    df.set_index('date').resample('M').sum()  # Monthly aggregation
    df['rolling_avg'] = df['revenue'].rolling(window=7).mean()

  Cohort analysis:
    df['cohort'] = df.groupby('customer_id')['order_date'].transform('min')

  Segmentation:
    from sklearn.cluster import KMeans
    kmeans = KMeans(n_clusters=4).fit(features)

STEP 5: AUTOMATED REPORTING
  Build scripts that:
  - Pull data from sources on a schedule
  - Apply transformations and analysis
  - Generate visualisations and export to files
  - Send email reports with attachments
  - Update dashboards or shared spreadsheets
  - Log execution and errors for monitoring

  Example pipeline:
    def daily_sales_report():
        df = extract_from_database()
        df = clean_and_transform(df)
        summary = calculate_kpis(df)
        create_visualisations(summary)
        send_email_report(summary, recipients)
        log_execution('daily_sales_report', status='success')

  Schedule with: cron (Linux), Task Scheduler (Windows), or Airflow

STEP 6: CODE QUALITY & BEST PRACTICES
  - Use version control (Git) for all analysis code
  - Write functions, not monolithic scripts (reusability)
  - Add docstrings explaining what each function does
  - Use config files for parameters (not hardcoded values)
  - Handle errors gracefully with try/except blocks
  - Log outputs and errors to files
  - Write unit tests for critical transformation functions
  - Code review: Have a peer review before deploying to production

TOOLS & RESOURCES
- Python 3.9+ with pandas, numpy, scipy, scikit-learn, matplotlib, seaborn
- Jupyter Notebook / JupyterLab / Google Colab
- VS Code with Python and Jupyter extensions
- Git for version control
- Airflow or cron for scheduling
- Virtual environments: venv, conda

QUALITY STANDARDS
- Code in version control: 100% of production scripts
- Error handling: All scripts handle failures gracefully with logging
- Documentation: README and docstrings for all functions
- Testing: Critical transformations have unit tests
- Reproducibility: Any analyst can run the code and get the same results
- Performance: Scripts complete within reasonable time (monitor runtime)
