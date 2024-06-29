# from decimal import Decimal
# import arrow
# from matplotlib.backends.backend_pdf import PdfPages
# import matplotlib.pyplot as plt
# import mplfinance as mpf
# import matplotlib.ticker as ticker

# from algorithems.analysis import get_profit_for_ratio
# from models.evaluation import EvaluationResults
# from models.trading import GroupRatio
# from utils.math_utils import D
# from utils.time_utils import get_business_days

# curr_precision = Decimal("Infinity")


# def fake_format_price(x: float, _: None = None) -> str:
#     def check_curr_precision(precision: Decimal) -> None:
#         global curr_precision
#         if curr_precision > precision:
#             curr_precision = precision

#     x_decimal = D(x)
#     if x_decimal % D("0.01") != D("0"):
#         check_curr_precision(Decimal("0.001"))
#         return str(x_decimal.quantize(Decimal("0.001")))
#     elif x_decimal % D("0.1") != D("0"):
#         check_curr_precision(Decimal("0.01"))
#         return str(x_decimal.quantize(Decimal("0.01")))
#     elif x_decimal % D("1") != D("0"):
#         check_curr_precision(Decimal("0.1"))
#         return str(x_decimal.quantize(Decimal("0.1")))
#     else:
#         check_curr_precision(Decimal("1"))
#         return str(x_decimal.quantize(Decimal("1")))


# def format_price(x: float, _: None = None) -> str:
#     global curr_precision
#     x_decimal = D(x)
#     return str(x_decimal.quantize(curr_precision))


# def save_results_to_graph_file(
#     ratio: GroupRatio,
#     evaluations_results: list[EvaluationResults],
#     duration: int,
#     path: str,
# ) -> None:
#     global curr_precision
#     evaluations_results = sorted(
#         evaluations_results,
#         key=lambda result: get_profit_for_ratio(
#             ratio.target_profit, ratio.stop_loss, result.data
#         ).value,
#         reverse=True,
#     )

#     start_date = min([result.evaluation.timestamp for result in evaluations_results])
#     end_date = max([result.evaluation.timestamp for result in evaluations_results])

#     average_trade_per_day = len(evaluations_results) / (
#         get_business_days(start_date, end_date) + 1
#     )

#     with PdfPages("fake_pdf.pdf") as fake_pdf:  # type: ignore
#         with PdfPages(path) as pdf:  # type: ignore
#             plt.figure()
#             plt.axis("off")
#             best_ratio_text = f"Target profit: {ratio.target_profit}, Stop loss: {ratio.stop_loss}, Average: {ratio.average}, Duration: {duration}"
#             dates_text = f"Start date: {start_date}, End date: {end_date}"
#             average_per_day_text = f"Average trades per day: {average_trade_per_day}"
#             plt.text(0.5, 0.6, best_ratio_text, ha="center", va="center")
#             plt.text(0.5, 0.5, dates_text, ha="center", va="center")
#             plt.text(0.5, 0.4, average_per_day_text, ha="center", va="center")
#             pdf.savefig()
#             plt.close()
#             for evaluation_result in evaluations_results:
#                 df = evaluation_result.df
#                 df["volume"] = df["volume"].astype(float)

#                 # fake
#                 fig, axis = mpf.plot(
#                     df,
#                     type="candle",
#                     returnfig=True,
#                     datetime_format="%H:%M",
#                 )
#                 axis[0].yaxis.set_major_formatter(
#                     ticker.FuncFormatter(fake_format_price)
#                 )
#                 fake_pdf.savefig(fig)
#                 plt.close()
#                 # real
#                 market_colors = mpf.make_marketcolors(up="g", down="r")
#                 style = mpf.make_mpf_style(marketcolors=market_colors)
#                 vwap = mpf.make_addplot(df["vwap"], type="line", width=1.5)
#                 fig, axis = mpf.plot(
#                     df,
#                     type="candle",
#                     returnfig=True,
#                     addplot=vwap,
#                     volume=True,
#                     style=style,
#                     datetime_format="%H:%M",
#                 )
#                 axis[0].yaxis.set_major_formatter(ticker.FuncFormatter(format_price))
#                 if fig is None:
#                     continue
#                 curr_profit = get_profit_for_ratio(
#                     ratio.target_profit, ratio.stop_loss, evaluation_result.data
#                 )
#                 entry_price = evaluation_result.df.iloc[0]["close"]
#                 entry_datetime = evaluation_result.df.iloc[
#                     0
#                 ].name.to_pydatetime()  # type: ignore
#                 text = f"symbol: {evaluation_result.evaluation.symbol}, date: {arrow.get(evaluation_result.evaluation.timestamp).format('DD-MM-YYYY HH:mm:ss')}"
#                 profit_text = f"entry price: {entry_price}, profit: {curr_profit.value:.4f}, time: {curr_profit.datetime - entry_datetime}"
#                 url = f"{evaluation_result.evaluation.url}"
#                 fig.text(0.01, 0.05, text)
#                 fig.text(0.55, 0.05, profit_text)
#                 fig.text(0.01, 0.02, url, fontsize=5)
#                 pdf.savefig(fig)
#                 plt.close()
#                 curr_precision = Decimal("Infinity")
