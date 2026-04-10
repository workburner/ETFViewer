def investment_growth(initial_amount, yearly_input, growth_rate, years):
    totals = []
    gains = []
    gain_percents = []
    yearly_gain_percents = []

    total = initial_amount

    for year in range(1, years + 1):
        total = (total + yearly_input) * (1 + growth_rate)

        invested = initial_amount + (yearly_input * year)
        gain_value = total - invested
        gain_percent = (gain_value / invested) * 100 if invested > 0 else 0
        yearly_gain_percent = (total/initial_amount) ** (1/year)

        totals.append(total)
        gains.append(gain_value)
        gain_percents.append(gain_percent)
        yearly_gain_percents.append(yearly_gain_percent)

    return totals, gains, gain_percents, yearly_gain_percents


# Example usage
initial_amount = 370000
yearly_input = 80000
growth_rate = 0.06
years = 5

totals, gains, gain_percents, yearly_gain_percents = investment_growth(
    initial_amount, yearly_input, growth_rate, years
)

print(f"{'Year':<6}"
      f"{'Invested ($)':>15}"
      f"{'Total ($)':>15}"
      f"{'Gain ($)':>15}"
      f"{'Gain (%)':>12}"
      f"{'Ann. (%)':>12}")
print("-" * 75)
for i in range(len(totals)):
    year = i + 1
    invested = initial_amount + yearly_input * year

    # CAGR formula
    if invested > 0:
        annualized = ((totals[i] / invested) ** (1 / year) - 1) * 100
    else:
        annualized = 0

    print(f"{year:<6}"
          f"{invested:>15,.2f}"
          f"{totals[i]:>15,.2f}"
          f"{gains[i]:>15,.2f}"
          f"{gain_percents[i]:>12.2f}"
          f"{annualized:>12.2f}")