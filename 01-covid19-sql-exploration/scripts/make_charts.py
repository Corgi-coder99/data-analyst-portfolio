"""Draw the README charts from the SQL views in covid.duckdb (run scripts/run_all.py first).

Usage (from project root):  python scripts/make_charts.py
Requires: pip install duckdb matplotlib
"""
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)
con = duckdb.connect(str(ROOT / "covid.duckdb"), read_only=True)

NAVY, TEAL, RED, GREY, ORANGE = "#1F3A5F", "#2A9D8F", "#D1495B", "#B8C2CC", "#F4A261"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 12, "figure.dpi": 130,
                     "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True})
millions = FuncFormatter(lambda v, _: f"{v / 1e6:.0f}M")


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved", name)


# 1. Global monthly cases vs. death rate (complete months only, from v_global_monthly)
m = con.execute("""SELECT month, new_cases, new_deaths, death_rate_pct FROM v_global_monthly
                   WHERE month < (SELECT MAX(month) FROM v_global_monthly) ORDER BY month""").fetchdf()
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.bar(m["month"], m["new_cases"], width=25, color=GREY, label="New cases (left)")
ax.yaxis.set_major_formatter(millions)
ax.set_ylabel("Monthly new cases")
ax2 = ax.twinx()
ax2.plot(m["month"], m["death_rate_pct"], color=RED, lw=2, label="Death rate % (right)")
ax2.set_ylim(0, 10)
ax2.set_ylabel("Reported deaths / cases (%)")
ax2.grid(False)
ax2.spines["right"].set_visible(True)
ax.set_title("Cases exploded in 2022, but the death rate collapsed")
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper right", frameon=False)
save(fig, "01_global_cases_vs_death_rate.png")

# 2. Continents: deaths per million (population-adjusted)
c = con.execute("""SELECT continent, SUM(total_deaths) AS deaths,
                          SUM(total_deaths) * 1e6 / SUM(population) FILTER (WHERE total_deaths IS NOT NULL) AS dpm
                   FROM v_country_summary GROUP BY continent ORDER BY dpm""").fetchdf()
fig, ax = plt.subplots(figsize=(7.5, 3.8))
bars = ax.barh(c["continent"], c["dpm"], color=[RED if v > 2500 else TEAL for v in c["dpm"]])
for b, d in zip(bars, c["deaths"]):
    ax.text(b.get_width() + 40, b.get_y() + b.get_height() / 2, f"{b.get_width():,.0f}  ({d / 1e6:.2f}M deaths)",
            va="center", fontsize=9)
ax.set_xlim(0, c["dpm"].max() * 1.45)
ax.set_xlabel("Deaths per million people")
ax.set_title("Adjusted for population, South America was hit hardest")
ax.grid(axis="y", visible=False)
save(fig, "02_continent_deaths_per_million.png")

# 3. Top 10 infection rates (countries with 1M+ people)
t = con.execute("""SELECT country, pct_population_infected FROM v_country_summary
                   WHERE population >= 1000000 AND pct_population_infected IS NOT NULL
                   ORDER BY pct_population_infected DESC LIMIT 10""").fetchdf().iloc[::-1]
fig, ax = plt.subplots(figsize=(7.5, 4.2))
ax.barh(t["country"], t["pct_population_infected"], color=NAVY)
for y, v in enumerate(t["pct_population_infected"]):
    ax.text(v + 0.6, y, f"{v:.1f}%", va="center", fontsize=9)
ax.set_xlim(0, 80)
ax.set_xlabel("% of population with a reported case")
ax.set_title("Top 10 countries by reported infection rate")
ax.grid(axis="y", visible=False)
save(fig, "03_top10_infection_rate.png")

# 4. Fully vaccinated, top 15 with Vietnam highlighted
v = con.execute("""SELECT country, pct_fully_vaccinated FROM v_country_summary
                   WHERE population >= 1000000 AND pct_fully_vaccinated IS NOT NULL
                   ORDER BY pct_fully_vaccinated DESC LIMIT 15""").fetchdf().iloc[::-1]
fig, ax = plt.subplots(figsize=(7.5, 5))
ax.barh(v["country"], v["pct_fully_vaccinated"], color=[ORANGE if x == "Vietnam" else TEAL for x in v["country"]])
for y, val in enumerate(v["pct_fully_vaccinated"]):
    ax.text(val + 0.4, y, f"{val:.1f}%", va="center", fontsize=9)
ax.set_xlim(60, 104)
ax.set_xlabel("% of population fully vaccinated")
ax.set_title("Vietnam ranks in the global top 10 for full vaccination")
ax.grid(axis="y", visible=False)
save(fig, "04_fully_vaccinated_top15.png")

# 5. Vietnam: 7-day average cases and vaccination coverage
vn = con.execute("SELECT date, new_cases_7d_avg FROM v_vietnam_timeline WHERE date < DATE '2023-07-01'").fetchdf()
vc = con.execute("""SELECT date, people_fully_vaccinated * 100.0 / population AS pct FROM v_vaccination_progress
                    WHERE country = 'Vietnam' AND people_fully_vaccinated IS NOT NULL
                      AND date < DATE '2023-07-01'""").fetchdf()
fig, ax = plt.subplots(figsize=(9, 4))
ax.fill_between(vn["date"], vn["new_cases_7d_avg"], color=RED, alpha=0.25)
ax.plot(vn["date"], vn["new_cases_7d_avg"], color=RED, lw=1.5, label="New cases, 7-day avg (left)")
ax.set_ylabel("Cases per day")
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x / 1e3:.0f}k"))
ax2 = ax.twinx()
ax2.plot(vc["date"], vc["pct"], color=NAVY, lw=2, label="Fully vaccinated % (right)")
ax2.set_ylim(0, 100); ax2.grid(False); ax2.spines["right"].set_visible(True)
ax2.set_ylabel("% of population")
ax.set_title("Vietnam: the big wave arrived after vaccination was already scaling up")
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False)
save(fig, "05_vietnam_cases_and_vaccination.png")
