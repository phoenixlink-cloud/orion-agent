---
name: statistical-analysis-hypothesis-testing
description: "Applying statistical methods to validate business hypotheses, identify"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - data
  - analytics
  - business-intelligence
  - data-analyst
---

SKILL: STATISTICAL ANALYSIS & HYPOTHESIS TESTING

SKILL ID:       DA-SK-002
ROLE:           Data Analyst
CATEGORY:       Statistical Methods
DIFFICULTY:     Advanced
ESTIMATED TIME: 4-16 hours per analysis (depending on complexity)

DESCRIPTION
Applying statistical methods to validate business hypotheses, identify
significant patterns, and quantify relationships in data. This covers
descriptive statistics, inferential statistics, A/B test analysis, regression,
and communicating statistical findings to non-technical stakeholders.

STEP-BY-STEP PROCEDURE

STEP 1: DEFINE THE HYPOTHESIS
  Null hypothesis (H0): "There is no difference / no relationship"
  Alternative hypothesis (H1): "There IS a difference / relationship"
  Example: H0: "The new landing page has the same conversion rate as the old one"
           H1: "The new landing page has a higher conversion rate"
  Set significance level: alpha = 0.05 (95% confidence) is standard

STEP 2: EXPLORATORY DATA ANALYSIS (EDA)
  Before formal testing, explore the data:
  - Descriptive statistics: Mean, median, mode, standard deviation, range
  - Distribution: Is the data normally distributed? (Shapiro-Wilk test, Q-Q plots)
  - Outliers: Box plots, IQR method, Z-scores (flag values > 3 SD)
  - Missing data: Patterns, percentage, imputation strategy
  - Visualise: Histograms, scatter plots, correlation matrices, time series plots
  - Sample size: Is the sample large enough for the intended analysis?

STEP 3: CHOOSE THE RIGHT TEST
  COMPARING MEANS:
  - 2 groups, normal data: Independent t-test
  - 2 groups, non-normal: Mann-Whitney U test
  - 2+ groups, normal: ANOVA (one-way or two-way)
  - 2+ groups, non-normal: Kruskal-Wallis test
  - Before/after (paired): Paired t-test or Wilcoxon signed-rank

  COMPARING PROPORTIONS:
  - 2 groups: Chi-squared test or Z-test for proportions
  - A/B tests: Chi-squared or Fisher's exact test

  RELATIONSHIPS:
  - Two continuous variables: Pearson correlation (linear) or Spearman (non-linear)
  - Predicting a continuous outcome: Linear regression
  - Predicting a binary outcome: Logistic regression
  - Multiple predictors: Multiple regression

STEP 4: CONDUCT THE ANALYSIS
  Using Python (pandas, scipy, statsmodels):
  - Import and prepare the data
  - Verify assumptions of the chosen test (normality, homogeneity of variance)
  - Run the test and capture: Test statistic, p-value, confidence interval, effect size
  - Interpret: p < 0.05 = statistically significant (reject H0)
  - Calculate effect size: Cohen's d, odds ratio, R-squared (significance != importance)
  - Check practical significance: Is the difference meaningful for the business?

STEP 5: A/B TEST ANALYSIS (Common use case)
  - Confirm: Was the test properly randomised? Adequate sample size?
  - Calculate: Conversion rate for control (A) and treatment (B)
  - Statistical test: Chi-squared or Z-test for proportions
  - Confidence interval: What is the range of the true difference?
  - Practical significance: Is a 0.5% improvement worth the cost of implementation?
  - Segment analysis: Does the effect vary by user segment?
  - Watch for: Peeking bias (checking results too early), novelty effect, selection bias

STEP 6: COMMUNICATE FINDINGS
  For non-technical stakeholders:
  - Lead with the business insight, not the statistics
  - "The new landing page increases conversions by 15% (95% confident it's between 8-22%)"
  - NOT: "We rejected the null hypothesis with p = 0.003 using a chi-squared test"
  - Use visualisations: Confidence interval plots, comparison charts
  - Include: Sample size, time period, caveats, and limitations
  - Recommend specific actions based on the findings
  - Be honest about uncertainty — confidence intervals matter more than p-values

TOOLS & RESOURCES
- Python: scipy.stats, statsmodels, pingouin, scikit-learn
- R: stats, lme4, ggplot2, broom
- Excel: Data Analysis ToolPak (basic statistics)
- A/B testing calculators: Evan Miller, Optimizely sample size calculator
- Visualisation: matplotlib, seaborn, plotly (Python); ggplot2 (R)
- Reference: "Naked Statistics" (Wheelan), "Statistics Done Wrong" (Reinhart)

QUALITY STANDARDS
- Correct test selection: Appropriate for the data type and question
- Assumptions checked: Normality, independence, sample size verified
- Effect size reported: Not just p-values (statistical vs. practical significance)
- Confidence intervals: Always included alongside point estimates
- Reproducibility: Code and data documented for anyone to replicate
- Communication: Findings presented in business language with visualisations
