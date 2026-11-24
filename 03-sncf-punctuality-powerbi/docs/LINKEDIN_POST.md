# LinkedIn post (draft)

The Power BI report exists in `powerbi/TGV_Punctuality.pbip` (screenshots in `assets/powerbi_*.png`). Open it, check it, and be ready to explain every visual and measure in an interview, because the post says you built it. Use `assets/powerbi_overview.png` as the first image, and `assets/powerbi_overview_filtered.png` as the second image to show the interactivity. Replace the placeholder `[start date]` in the post. The GitHub and live-dashboard links in the first comment are already filled in. Put the Overview page screenshot (or a short screen recording of you clicking an axis and the whole page filtering) as the first image, and the GitHub link in the first comment rather than in the post body, since LinkedIn tends to show posts with outbound links to fewer people.

---

🚄 How punctual is the TGV, really? I analysed 8 years of SNCF open data in Power BI

I built an interactive dashboard on 3.4 million TGV train runs across 146 routes (January 2018 to September 2026) to find out where punctuality breaks down.

The dashboard has 3 pages:
1. Home: the headline findings
2. Overview: KPIs, trends by month, quarter and year, outcome of every planned train
3. Routes & Causes: ranked routes, causes of delays, seasonality heatmap

What the data shows:
✅ 3.5M planned trains | 3.0% cancelled | 14.7% arrived late
✅ Late arrivals fell from 17.8% (2018) to 11.3% (2021), then climbed back. January to September 2026 is at 18.7%, against 14.3% in 2025
✅ When a train is late, it is later: 30.7 minutes on average in 2018, 40.4 in 2026. Trains more than 60 minutes late doubled from 1.5% (2021) to 3.1% (2026)
✅ July is the weakest month (18.5% late, against 12.2% in March)
✅ Routes that skip Paris are the least reliable: 19.5% late, against 14.0% for routes with a Paris terminal
✅ Cancellations spike with disruption: 53.6% in April 2020, 37.5% in April 2021, 32.7% in April 2018
✅ No single cause dominates: external causes, traffic management, infrastructure and rolling stock each explain about a fifth of late trains

What makes it interactive?
Click an axis (Atlantic, South-East, North, East, Cross-country, International) and every KPI, chart and table updates. You can also slice by service, journey length and year.

Honest limits, because they matter:
⚠️ The source counts a train once per route it serves, so these are route-level movements, not SNCF's official network regularity.
⚠️ Cause shares are an estimate built from the percentages SNCF publishes per route and month.
⚠️ I cleaned 388 rows where delay thresholds contradicted each other (for example, more trains over 60 minutes late than over 30). Every rule is logged in the repo.

Tools: Power BI | DAX | Data cleaning | Data modelling (star schema) | Python (pandas)

This project pushed me to think about KPI design: ratios of sums instead of averages of rates, and clear definitions before any chart.

I am looking for an internship or a work-study contract (alternance) in data analysis in Île-de-France from [start date]. If your team works with operational or transport data, I would love to talk.

What other insight would you add to this dashboard?

#PowerBI #DataAnalytics #DataVisualization #BusinessIntelligence #SNCF #OpenData #DAX #DataAnalyst #Alternance #Portfolio

---

First comment (paste the links here): Full project, data cleaning log and DAX measures: https://github.com/Corgi-coder99/data-analyst-portfolio/tree/main/03-sncf-punctuality-powerbi | Try the interactive version in your browser: https://corgi-coder99.github.io/data-analyst-portfolio/03-sncf-punctuality-powerbi/dashboard/index.html
