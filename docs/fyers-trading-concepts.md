# Fyers API: Core Trading Concepts

This document provides a high-level overview of the core concepts governing trading through the Fyers API. A clear understanding of these principles is fundamental to building any automated trading logic on the platform.

## The Core Principle: `productType`

The entire scheme of trading on Fyers revolves around a single, critical parameter specified with every order: the **`productType`**. This parameter informs Fyers of your intention for the trade and dictates how cash, margin, and risk are managed for that position.

The main product types are:

1.  **`CNC` (Cash and Carry):** For equity delivery. You intend to buy stocks and hold them for more than one day.
2.  **`INTRADAY`** (also known as `MIS` - Margin Intraday Square off): For leveraging your capital to trade equities or F&O with the mandatory condition that all positions will be closed by the end of the day.
3.  **`MARGIN`** (also known as `NRML` - Normal Margin): For holding leveraged overnight positions, primarily in Futures & Options (F&O).
4.  **`CO` (Cover Order) & `BO` (Bracket Order):** Special intraday order types that require a compulsory stop-loss, offering higher leverage in return for this reduced risk.

---

## 1. Cash Management (for `CNC` Orders)

This is the simplest model, used for investing in stocks for delivery.

*   **How it Works:** When you place a `CNC` buy order, the Fyers Risk Management System (RMS) checks if you have **100% of the trade value** (`quantity * price`) as free, withdrawable cash in your account.
*   **No Leverage:** There is no leverage. To buy ₹50,000 worth of Reliance shares, you must have ₹50,000 of cash.
*   **Settlement:** After the trade, the cash is debited from your ledger. On T+1 day, the shares are credited to your Demat account and will appear in your "Holdings".
*   **Selling:** When you sell from your holdings, the cash is credited to your account, but there's a settlement period (T+1) before it becomes fully withdrawable.

---

## 2. Margin Management (for `INTRADAY` and `MARGIN` Orders)

This is where leverage comes into play. Instead of paying the full value of the trade, you only need to put up a fraction of it, known as the **margin**.

*   **How it Works:** When you place an `INTRADAY` or `MARGIN` order, the Fyers RMS checks your **"Available Margin"**. This is a combination of your cash balance and the value of any stocks you've pledged as collateral.
*   **Margin Calculation:**
    *   **For Intraday Equity:** The margin is a percentage of the trade value, determined by Fyers based on the stock's volatility (e.g., 20% for a 5x leverage).
    *   **For F&O:** The margin is calculated based on the exchange's **SPAN + Exposure** margin requirements. SPAN calculates the worst-case loss scenario, and Exposure is an additional buffer.
*   **The `/funds` Endpoint:** The Fyers API's `/funds` endpoint is crucial here. It doesn't just show your cash balance. It shows a detailed breakdown of your total "Available Margin," which is the number the RMS checks against for leveraged trades.

---

## 3. Position Management

How your open positions are managed depends entirely on the `productType` you used to create them. The `/positions` API endpoint will show you all your open trades, clearly marked with their `productType`.

*   **`CNC` Positions:**
    *   These are not technically "open positions" in the trading sense after the settlement day. They become part of your **Holdings** (visible via the `/holdings` endpoint) and can be held indefinitely.

*   **`INTRADAY`, `CO`, `BO` Positions:**
    *   These are temporary positions that **must be closed the same day**.
    *   If you do not close them yourself, the Fyers RMS will **automatically square them off** at a designated time, typically around 3:15 PM IST. This is a mandatory rule to manage the risk of the leverage provided.

*   **`MARGIN` (F&O) Positions:**
    *   These are leveraged positions that you **can hold overnight**.
    *   You must maintain sufficient margin in your account every day to hold them. If your account value drops and the margin is insufficient, you will receive a margin call from Fyers.

---

## Summary: The Trading Workflow

For a retail trader using the API, the workflow is a continuous loop governed by these rules:

1.  **Check Funds:** Before trading, you call the `/funds` endpoint to see your available cash (for `CNC`) and available margin (for leveraged trades).
2.  **Place Order with Intent:** You place an order using the `/orders` endpoint, making a conscious decision about the `productType` (`CNC`, `INTRADAY`, etc.).
3.  **RMS Validation:** The Fyers RMS checks your order against your available funds/margin and the product type rules.
4.  **Position Creation:** If the order is executed, a position is created. You can view it by calling the `/positions` endpoint.
5.  **Position Lifecycle:** The fate of your position is now tied to its `productType`. It will either be auto-squared-off at the end of the day (`INTRADAY`) or carried forward (`MARGIN`/`CNC`), assuming you have the required funds/margin.