# 📊 RoomOps - Management Dashboard & Raporlama Eğitimi

## 👥 Hedef Kitle
- General Manager (GM)
- Chief Financial Officer (CFO) / Muhasebe Müdürü
- Revenue Manager
- Financial Controller
- Operations Manager

**Süre:** 2.5-3 saat
**Seviye:** İleri / Yönetim

---

## 📋 İçindekiler

1. [Executive Dashboard](#executive-dashboard)
2. [Financial Reports](#financial-reports)
3. [Revenue Management](#revenue-management)
4. [Operational Analytics](#operational-analytics)
5. [Forecasting & Budgeting](#forecasting--budgeting)
6. [Custom Reports](#custom-reports)

---

## Executive Dashboard

### 1.1 GM Dashboard Genel Bakış

**Dashboard bileşenleri:**

```
┌─────────────────────────────────────────────────────────────┐
│ 📊 Executive Dashboard - January 15, 2025                   │
│ Grand Canyon Hotel                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 🏨 Today's Flash Report                                     │
│ ┌──────────────┬──────────────┬──────────────┬───────────┐ │
│ │  Occupancy   │   Available  │   Revenue    │    ADR    │ │
│ │     87.5%    │    5 rooms   │  $6,450.00   │ $169.74   │ │
│ │   ▲ 2.3%     │              │  ▲ $450      │ ▲ $12     │ │
│ └──────────────┴──────────────┴──────────────┴───────────┘ │
│                                                             │
│ 📈 Key Performance Indicators (MTD)                         │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ RevPAR: $148.28 (▲ 5.2% vs LY)                         │ │
│ │ GOPPAR: $89.50 (▲ 3.8% vs LY)                          │ │
│ │ Guest Satisfaction: 9.2/10 (▲ 0.3)                     │ │
│ │ Staff Efficiency: 94% (▼ 1.2%)                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ 💰 Revenue Breakdown (MTD)                                  │
│ ┌──────────────────────────────────────┐                   │
│ │ Room Revenue      $156,780  (65%)    │ ███████████       │
│ │ F&B Revenue       $52,340   (22%)    │ ████              │
│ │ Spa & Services    $18,920   (8%)     │ ██                │
│ │ Other Revenue     $11,960   (5%)     │ █                 │
│ │ Total:           $240,000            │                   │
│ └──────────────────────────────────────┘                   │
│                                                             │
│ 🎯 Department Performance                                   │
│ Front Office:     ⭐⭐⭐⭐⭐ (98%)                            │
│ Housekeeping:     ⭐⭐⭐⭐⭐ (96%)                            │
│ F&B:              ⭐⭐⭐⭐☆ (92%)                            │
│ Finance:          ⭐⭐⭐⭐⭐ (99%)                            │
│                                                             │
│ [Detailed View] [Export PDF] [Schedule Email]              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 1.2 Dashboard Metrikleri Açıklamaları

#### Occupancy Rate (Doluluk Oranı)
```
Formula: (Occupied Rooms / Total Available Rooms) × 100

Example:
35 occupied rooms / 40 total rooms = 87.5%

💡 Best Practice: Target 85%+ on weekdays, 95%+ on weekends
```

#### ADR (Average Daily Rate)
```
Formula: Room Revenue / Rooms Sold

Example:
$6,450 room revenue / 38 rooms sold = $169.74

💡 Benchmark: Compare with comp set (competitive set)
```

#### RevPAR (Revenue Per Available Room)
```
Formula: Room Revenue / Total Available Rooms
Or: ADR × Occupancy Rate

Example:
$6,450 / 40 rooms = $161.25
Or: $169.74 × 0.875 = $148.52

💡 Key Metric: Best indicator of revenue performance
```

#### GOPPAR (Gross Operating Profit Per Available Room)
```
Formula: Gross Operating Profit / Total Available Rooms

Example:
Gross Profit: $3,580
Total Rooms: 40
GOPPAR: $89.50

💡 Profitability: Higher GOPPAR = better profitability
```

---

### 1.3 Daily Flash Report

**Accessing Flash Report:**
```
Dashboard → Reports → Daily Flash Report
```

**Report Contents:**

```
📊 DAILY FLASH REPORT
Date: January 15, 2025
Property: Grand Canyon Hotel (50 rooms)

═══════════════════════════════════════════════════════════

📈 OCCUPANCY STATISTICS

Today:
├─ Occupied Rooms: 35 (87.5%)
├─ Available: 5
├─ Out of Order: 0
├─ Complimentary: 2
└─ House Use: 0

Movements:
├─ Arrivals: 12
├─ Departures: 8
├─ Stayovers: 23
├─ No-shows: 0
└─ Early Departures: 0

Last Year Same Date:
├─ Occupancy: 85.2% (↑ 2.3%)
├─ ADR: $157.50 (↑ $12.24)
└─ RevPAR: $134.19 (↑ $14.09)

═══════════════════════════════════════════════════════════

💰 REVENUE SUMMARY

Room Revenue:
├─ Actual: $6,450.00
├─ Budgeted: $6,200.00
├─ Variance: +$250.00 (+4.0%) ✅
└─ Last Year: $6,000.00 (+7.5%)

Other Revenue:
├─ F&B: $1,850.00
├─ Minibar: $345.00
├─ Spa: $680.00
├─ Laundry: $125.00
└─ Other: $200.00

Total Revenue: $9,650.00
Budget: $9,100.00 (+$550 / +6.0%) ✅

═══════════════════════════════════════════════════════════

📊 RATE ANALYSIS

Average Rate: $169.74
Rate Mix:
├─ BAR (Best Available): 45% @ $185
├─ Corporate: 25% @ $155
├─ Government: 10% @ $135
├─ Group: 15% @ $145
└─ Other: 5% @ $165

Rate Overrides: 3 (with approval)
Discounts Applied: $420.00 (6.1% of potential revenue)

═══════════════════════════════════════════════════════════

🎯 MARKET SEGMENT ANALYSIS

Segment Distribution:
├─ Transient: 55% (ADR: $175)
├─ Corporate: 30% (ADR: $155)
├─ Group: 10% (ADR: $145)
└─ Wholesale: 5% (ADR: $135)

Top Sources:
1. Direct: 40%
2. OTA: 35%
3. Corporate: 20%
4. Walk-in: 5%

═══════════════════════════════════════════════════════════

📅 FORECAST (Next 7 Days)

Date          Occ%    Avail   ADR      RevPAR    Notes
───────────────────────────────────────────────────────────
Jan 16 (Thu)  92%     4       $172     $158      Regular
Jan 17 (Fri)  95%     2       $189     $179      High
Jan 18 (Sat)  98%     1       $195     $191      Peak
Jan 19 (Sun)  88%     6       $165     $145      Normal
Jan 20 (Mon)  82%     9       $160     $131      Low
Jan 21 (Tue)  85%     7       $165     $140      Regular
Jan 22 (Wed)  87%     6       $168     $146      Regular

7-Day Avg:    89.6%   5       $173     $156

═══════════════════════════════════════════════════════════

⚠️ ALERTS & ACTION ITEMS

1. 🟢 Occupancy above budget (+2.3%) - excellent!
2. 🟡 Weekend rates opportunity - consider yield management
3. 🔴 Monday/Tuesday soft - promotional campaign needed
4. 🟢 Guest satisfaction high (9.2/10) - maintain quality
5. 🟡 OTA commission costs increasing - review strategy

═══════════════════════════════════════════════════════════

Prepared by: System
Time: 06:00 AM
Next update: Tomorrow 06:00 AM
```

---

## Financial Reports

### 2.1 P&L Report (Profit & Loss)

**Accessing P&L:**
```
Reports → Financial → P&L Report
Period: Select (Daily, Monthly, YTD, Custom)
```

**P&L Statement Example (Monthly):**

```
═══════════════════════════════════════════════════════════
              PROFIT & LOSS STATEMENT
              Grand Canyon Hotel
              January 2025
═══════════════════════════════════════════════════════════

REVENUE
─────────────────────────────────────────────────────────
Room Revenue                      $240,000    100.0%
  Less: Allowances                ($2,400)     (1.0%)
Net Room Revenue                  $237,600     99.0%

Food Revenue                      $45,000      18.8%
Beverage Revenue                  $22,000       9.2%
Other Operating Departments       $18,000       7.5%
─────────────────────────────────────────────────────────
TOTAL REVENUE                     $322,600    134.4%

DEPARTMENTAL EXPENSES
─────────────────────────────────────────────────────────
Rooms Department:
  Payroll & Related               $32,400      13.5%
  Other Expenses                  $14,280       6.0%
Total Rooms Expense               $46,680      19.5%

F&B Department:
  Payroll & Related               $26,800      11.2%
  Cost of Sales                   $20,100       8.4%
  Other Expenses                  $6,030        2.5%
Total F&B Expense                 $52,930      22.1%

Other Departments                  $9,000       3.8%
─────────────────────────────────────────────────────────
TOTAL DEPARTMENTAL EXPENSE        $108,610     45.3%

DEPARTMENTAL PROFIT               $213,990     89.2%

UNDISTRIBUTED OPERATING EXPENSES
─────────────────────────────────────────────────────────
Administrative & General          $29,088      12.1%
Sales & Marketing                 $25,808      10.8%
Property Operations & Maintenance $16,130       6.7%
Utilities                         $12,904       5.4%
─────────────────────────────────────────────────────────
TOTAL UNDISTRIBUTED EXPENSES      $83,930      35.0%

GROSS OPERATING PROFIT (GOP)      $130,060     54.2%

MANAGEMENT FEES                   $9,678        4.0%
INCOME BEFORE FIXED CHARGES       $120,382     50.1%

FIXED CHARGES
─────────────────────────────────────────────────────────
Property Taxes                    $8,065        3.4%
Insurance                         $6,452        2.7%
Depreciation & Amortization       $19,356       8.1%
─────────────────────────────────────────────────────────
TOTAL FIXED CHARGES               $33,873      14.1%

NET OPERATING INCOME (NOI)        $86,509      36.0%
═══════════════════════════════════════════════════════════

KEY RATIOS:
─────────────────────────────────────────────────────────
GOP Margin:                        54.2%  (Target: 50%)  ✅
Flow-through:                      65.3%  (Target: 60%)  ✅
Labor Cost % (Rooms):              13.5%  (Target: 15%)  ✅
F&B Cost %:                        30.0%  (Target: 32%)  ✅
═══════════════════════════════════════════════════════════

COMPARISON TO BUDGET:
─────────────────────────────────────────────────────────
                        Actual      Budget      Variance
─────────────────────────────────────────────────────────
Total Revenue          $322,600    $310,000    +$12,600 ✅
GOP                    $130,060    $125,000    +$5,060  ✅
NOI                    $86,509     $82,000     +$4,509  ✅
─────────────────────────────────────────────────────────

COMMENTARY:
• Strong performance across all departments
• Room revenue exceeded budget by 4.1%
• GOP margin improved by 2.2 points vs. LY
• Cost controls effective in Rooms department
• Utility costs slightly higher - monitor

Prepared by: Finance Department
Date: February 1, 2025
```

---

### 2.2 Cash Flow Report

**Purpose:** Track cash in/out for liquidity management

```
═══════════════════════════════════════════════════════════
              CASH FLOW STATEMENT
              January 2025
═══════════════════════════════════════════════════════════

BEGINNING CASH BALANCE (Jan 1)                   $45,000

OPERATING ACTIVITIES
─────────────────────────────────────────────────────────
Cash Receipts:
  Room Revenue                   $225,300
  F&B Revenue                    $64,200
  Other Revenue                  $17,100
Total Cash Receipts                              $306,600

Cash Payments:
  Payroll                       ($85,400)
  Suppliers                     ($42,800)
  Utilities                     ($12,900)
  Other Operating               ($38,200)
Total Cash Payments                             ($179,300)

Net Cash from Operations                         $127,300

INVESTING ACTIVITIES
─────────────────────────────────────────────────────────
Equipment Purchase                                ($18,000)
Furniture Replacement                             ($8,500)
Net Cash from Investing                          ($26,500)

FINANCING ACTIVITIES
─────────────────────────────────────────────────────────
Loan Payment                                      ($15,000)
Interest Paid                                     ($2,800)
Net Cash from Financing                          ($17,800)

NET INCREASE IN CASH                              $83,000

ENDING CASH BALANCE (Jan 31)                     $128,000
═══════════════════════════════════════════════════════════

CASH POSITION ANALYSIS:
─────────────────────────────────────────────────────────
Operating Cash Flow Ratio:         2.85x  ✅ Healthy
Days Cash on Hand:                 45 days ✅ Good
Current Ratio:                     2.1:1   ✅ Strong
Quick Ratio:                       1.8:1   ✅ Strong
─────────────────────────────────────────────────────────

💡 INSIGHTS:
• Strong operating cash flow (+$127K)
• Cash position improved significantly
• Good liquidity for operations
• Consider investing excess cash
═══════════════════════════════════════════════════════════
```

---

### 2.3 Accounts Receivable Aging

**Purpose:** Track outstanding payments from corporate clients

```
═══════════════════════════════════════════════════════════
          ACCOUNTS RECEIVABLE AGING REPORT
          As of January 31, 2025
═══════════════════════════════════════════════════════════

Company Name      Total     Current   1-30d   31-60d   61-90d   90+d
─────────────────────────────────────────────────────────────────
ABC Corp         $12,500   $8,000    $3,000  $1,500    $0       $0
XYZ Industries   $8,750    $6,250    $2,500   $0       $0       $0
Tech Solutions   $15,200   $10,000   $3,200  $2,000    $0       $0
Global Trading   $3,450    $0        $1,200  $1,250   $1,000    $0
Hotel Partners   $22,100   $18,000   $4,100   $0       $0       $0
Others           $18,000   $14,500   $2,800  $700      $0       $0
─────────────────────────────────────────────────────────────────
TOTAL           $80,000   $56,750   $16,800 $5,450   $1,000    $0
Percentage       100%      70.9%     21.0%   6.8%     1.3%     0%
─────────────────────────────────────────────────────────────────

AGING ANALYSIS:
─────────────────────────────────────────────────────────────────
✅ Current (0-30 days):        91.9%    Excellent
⚠️ Past Due (31-60 days):       6.8%    Monitor
🔴 Seriously Past Due (61+):    1.3%    Action Required
─────────────────────────────────────────────────────────────────

ACTION ITEMS:
1. 🔴 URGENT: Global Trading - $1,000 overdue 61+ days
   → Call today, payment plan needed

2. 🟡 Tech Solutions - Follow up on $2,000 (31-60 days)
   → Reminder email sent

3. ✅ ABC Corp - Good payment history, no action needed

COLLECTION TARGETS:
─────────────────────────────────────────────────────────────────
This Month: Collect $22,250 (past due amounts)
Target Collection Rate: 95%
Days Sales Outstanding (DSO): 28 days (Target: 30) ✅
═══════════════════════════════════════════════════════════════
```

---

## Revenue Management

### 3.1 Pricing Analytics

**Accessing RMS:**
```
RMS → Pricing Dashboard
```

**Pricing Dashboard:**

```
═══════════════════════════════════════════════════════════
           REVENUE MANAGEMENT DASHBOARD
           January 15, 2025
═══════════════════════════════════════════════════════════

📊 CURRENT PRICING STRATEGY

Today's Rates:
┌────────────────┬──────────┬──────────┬──────────┬─────────┐
│ Room Type      │ BAR Rate │ Occupancy│ Available│ Status  │
├────────────────┼──────────┼──────────┼──────────┼─────────┤
│ Standard       │  $165    │   90%    │    2     │ ⬆️ Raise│
│ Deluxe         │  $185    │   88%    │    3     │ ⬆️ Raise│
│ Suite          │  $285    │   75%    │    2     │ ➡️ Hold │
└────────────────┴──────────┴──────────┴──────────┴─────────┘

🎯 PRICING RECOMMENDATIONS (AI-Generated)

Tomorrow (Jan 16):
├─ Standard: $165 → $175 (+$10, +6.1%) ⬆️
│  Confidence: 92% (High demand detected)
│  Reason: High occupancy, limited availability
│
├─ Deluxe: $185 → $195 (+$10, +5.4%) ⬆️
│  Confidence: 88% (Event in city)
│  Reason: Conference at convention center
│
└─ Suite: $285 → $285 (No change) ➡️
   Confidence: 65% (Moderate demand)
   Reason: Maintain current positioning

Weekend (Jan 18-19):
├─ Standard: $195 (Peak pricing) 📈
├─ Deluxe: $215 (Peak pricing) 📈
└─ Suite: $325 (Peak pricing) 📈

Forecast Revenue Impact:
├─ Current Pricing: $9,200
├─ Recommended: $10,150
└─ Potential Gain: +$950 (+10.3%)

[Apply Recommendations] [Customize] [View Forecast]

═══════════════════════════════════════════════════════════

📈 COMPETITOR ANALYSIS

Comp Set Pricing (Today):
┌────────────────────────┬──────────┬───────────┬─────────┐
│ Hotel                  │ Standard │ Occupancy │ Position│
├────────────────────────┼──────────┼───────────┼─────────┤
│ Your Hotel            │  $165    │   87.5%   │  ---    │
│ Competitor A (4-star) │  $155    │   92%     │ Below ⬇│
│ Competitor B (4-star) │  $175    │   85%     │ Above ⬆│
│ Competitor C (5-star) │  $210    │   78%     │ Above ⬆│
└────────────────────────┴──────────┴───────────┴─────────┘

Market Position: At Market
Price Index: 100 (Fair pricing vs. quality)

💡 INSIGHT: Room to increase rates while maintaining 
            competitive position

═══════════════════════════════════════════════════════════

📊 DEMAND FORECAST (30 Days)

Demand Level:
Jan 16-20: 🟡 Moderate (82-87% occupancy)
Jan 21-25: 🟢 High (90-95% occupancy)
Jan 26-31: 🟡 Moderate (85-90% occupancy)
Feb 1-5:   🔴 Low (70-75% occupancy)

Recommended Strategy:
├─ Jan 16-20: Gradual rate increase
├─ Jan 21-25: Peak pricing, minimum discounts
├─ Jan 26-31: Maintain rates, selective discounts
└─ Feb 1-5: Promotional rates, packages

═══════════════════════════════════════════════════════════
```

---

### 3.2 Rate Strategy & Optimization

**Best Practices:**

```
1️⃣ DYNAMIC PRICING RULES

📈 Increase Rates When:
   ├─ Occupancy >85%
   ├─ <7 days to arrival
   ├─ Events in city
   ├─ Comp set rates up
   └─ High booking pace

📉 Decrease Rates When:
   ├─ Occupancy <70%
   ├─ >30 days to arrival
   ├─ Slow booking pace
   ├─ Excess inventory
   └─ Need to stimulate demand

═══════════════════════════════════════════════════════════

2️⃣ RATE RESTRICTIONS

Minimum Length of Stay (MinLOS):
├─ Peak dates: 2-3 nights
├─ Regular dates: 1 night
└─ Low season: No restriction

Closed to Arrival (CTA):
├─ Use on peak nights
├─ Force multi-night bookings
└─ Maximize revenue

Advanced Purchase:
├─ 7-day advance: 10% off
├─ 14-day advance: 15% off
├─ 30-day advance: 20% off
└─ Non-refundable rates

═══════════════════════════════════════════════════════════

3️⃣ CHANNEL MANAGEMENT

Channel Priority:
1. Direct (Website) - 0% commission ✅
2. Corporate Direct - Negotiated rate
3. GDS - 10-12% commission
4. OTA - 15-20% commission
5. Wholesale - 20-25% commission

Rate Parity:
├─ Maintain rate parity across channels
├─ Exception: Direct booking incentive
└─ Monitor OTA compliance

═══════════════════════════════════════════════════════════

4️⃣ SEGMENT OPTIMIZATION

Segment Mix Target:
├─ Transient: 55-60% (High ADR)
├─ Corporate: 25-30% (Stable, volume)
├─ Group: 10-15% (Volume, lower ADR)
└─ Wholesale: 5-10% (Last resort)

Displacement Analysis:
When to accept group?
├─ Calculate: Group ADR vs. Transient ADR
├─ Consider: Ancillary revenue (F&B, spa)
└─ Decide: Accept if total value > transient

Example:
Group offers: $120/night for 20 rooms
Transient forecast: $160/night at 80% occupancy
Should we accept?

Analysis:
Group Revenue: $120 × 20 = $2,400
Transient Revenue: $160 × 16 (80% of 20) = $2,560

Decision: Reject group, keep rooms for transient
          (Unless group brings F&B revenue >$160)

═══════════════════════════════════════════════════════════
```

---

### 3.3 Pickup Pace Report

**Purpose:** Track booking pace vs. historical

```
═══════════════════════════════════════════════════════════
           PICKUP PACE REPORT
           Arrival Date: February 14, 2025 (Valentine's Day)
═══════════════════════════════════════════════════════════

BOOKING PACE COMPARISON

Days Before    Current   Last Year   2 Years Ago   Average
Arrival        Bookings  Bookings    Bookings      Variance
───────────────────────────────────────────────────────────
90-60 days       15         12           10         +30%  ⬆️
59-30 days       22         18           15         +28%  ⬆️
29-14 days       12         10            9         +23%  ⬆️
13-7 days         5          8            7         -20%  ⬇️
6-0 days          0          4            5          N/A
───────────────────────────────────────────────────────────
Total OTB        54         52           46         +13%  ⬆️
(On The Books)

Current OTB:     54 rooms (108% occupancy) 🎯
Available:       -4 rooms (OVERSOLD)
Forecast Final:  50 rooms (100% occupancy)

═══════════════════════════════════════════════════════════

📊 PACE INDICATORS

Pace vs. Last Year:    +13% (Ahead) ✅
Pace vs. 2 Years Ago:  +17% (Ahead) ✅
Pace vs. Budget:       +8% (Above target) ✅

Trend: 📈 Strong upward trend
       Booking pace accelerating

═══════════════════════════════════════════════════════════

🎯 ACTIONS RECOMMENDED

1. ✅ DONE: Rates increased to $225 (peak pricing)
2. ⚠️ TODO: Implement 2-night minimum stay
3. ⚠️ TODO: Close lowest rate codes
4. ⚠️ TODO: Manage overbooking (release 4 rooms)

Expected Outcome:
├─ Final ADR: $225-$235
├─ Occupancy: 100%
└─ RevPAR: $225-$235

═══════════════════════════════════════════════════════════
```

---

## Operational Analytics

### 4.1 Operational Efficiency Metrics

```
═══════════════════════════════════════════════════════════
        OPERATIONAL EFFICIENCY DASHBOARD
        January 2025
═══════════════════════════════════════════════════════════

🏨 FRONT OFFICE METRICS

Average Check-in Time:         4.2 minutes  ✅ (Target: <5m)
Average Check-out Time:        3.8 minutes  ✅ (Target: <5m)
Guest Satisfaction (Front Desk): 9.4/10    ✅ (Target: >9.0)

No-show Rate:                  1.2%         ✅ (Target: <2%)
Early Departure Rate:          0.8%         ✅ (Target: <1%)
Booking Modification Rate:     8.5%         ⚠️ (Target: <7%)

Staff Productivity:
├─ Bookings per staff:         45/day      ✅
├─ Check-ins per staff:        18/day      ✅
└─ Calls handled per staff:    52/day      ✅

═══════════════════════════════════════════════════════════

🧹 HOUSEKEEPING METRICS

Average Room Cleaning Time:    28 minutes   ✅ (Target: <30m)
Rooms Cleaned per Staff:       14.2/day     ✅ (Target: >12)
First-time Pass Rate:          96%          ✅ (Target: >95%)

Room Status Accuracy:          98.5%        ✅ (Target: >98%)
Guest Complaints (Cleanliness): 0.3%        ✅ (Target: <1%)

Task Completion Rate:          97%          ✅ (Target: >95%)
On-time Task Completion:       94%          ⚠️ (Target: >95%)

═══════════════════════════════════════════════════════════

💰 FINANCIAL EFFICIENCY

Invoice Processing Time:       2.1 days     ✅ (Target: <3d)
Payment Collection Rate:       96.5%        ✅ (Target: >95%)
Days Sales Outstanding (DSO):  28 days      ✅ (Target: <30d)

Accounts Receivable Aging:
├─ Current (0-30d):           92%          ✅
├─ 31-60 days:                6%           ✅
└─ 61+ days:                  2%           ⚠️

Cost Control:
├─ Labor Cost % (Rooms):      13.5%        ✅ (Target: <15%)
├─ Utility Cost per Room:     $8.50        ✅ (Target: <$10)
└─ Supply Cost per Room:      $4.20        ✅ (Target: <$5)

═══════════════════════════════════════════════════════════

📞 GUEST SERVICES

Average Response Time:         1.8 rings    ✅ (Target: <3)
Call Abandonment Rate:         2.1%         ✅ (Target: <5%)
Guest Request Resolution:      97%          ✅ (Target: >95%)

Service Recovery:
├─ Complaints Received:       12/month     ⚠️
├─ Resolved Same Day:         92%          ✅
└─ Escalations:               1            ✅

Guest Loyalty:
├─ Return Guest Rate:         32%          ✅ (Target: >30%)
├─ Referral Rate:            15%          ✅
└─ Online Reviews:           4.6/5 stars  ✅

═══════════════════════════════════════════════════════════
```

---

### 4.2 Department Performance Scorecard

```
═══════════════════════════════════════════════════════════
        DEPARTMENT PERFORMANCE SCORECARD
        January 2025
═══════════════════════════════════════════════════════════

🏆 FRONT OFFICE
─────────────────────────────────────────────────────────
KPI                    Actual    Target    Status
─────────────────────────────────────────────────────────
Guest Satisfaction      9.4/10    9.0/10    ⭐⭐⭐⭐⭐
Upsell Conversion       18%       15%       ⭐⭐⭐⭐⭐
No-show Rate           1.2%      <2%       ⭐⭐⭐⭐⭐
Check-in Time          4.2min    <5min     ⭐⭐⭐⭐⭐

Overall Score: 98/100 ⭐⭐⭐⭐⭐ EXCELLENT

═══════════════════════════════════════════════════════════

🧹 HOUSEKEEPING
─────────────────────────────────────────────────────────
KPI                    Actual    Target    Status
─────────────────────────────────────────────────────────
Cleanliness Score      9.2/10    9.0/10    ⭐⭐⭐⭐⭐
Cleaning Time          28min     <30min    ⭐⭐⭐⭐⭐
First-time Pass        96%       >95%      ⭐⭐⭐⭐⭐
Productivity           14.2rm    >12rm     ⭐⭐⭐⭐⭐

Overall Score: 96/100 ⭐⭐⭐⭐⭐ EXCELLENT

═══════════════════════════════════════════════════════════

🍽️ F&B
─────────────────────────────────────────────────────────
KPI                    Actual    Target    Status
─────────────────────────────────────────────────────────
Food Quality           8.9/10    9.0/10    ⭐⭐⭐⭐☆
Service Rating         9.1/10    9.0/10    ⭐⭐⭐⭐⭐
Revenue per Cover      $42.50    $40.00    ⭐⭐⭐⭐⭐
Food Cost %            28%       <30%      ⭐⭐⭐⭐⭐

Overall Score: 92/100 ⭐⭐⭐⭐☆ VERY GOOD

═══════════════════════════════════════════════════════════

💰 FINANCE
─────────────────────────────────────────────────────────
KPI                    Actual    Target    Status
─────────────────────────────────────────────────────────
Invoice Accuracy       99.5%     >99%      ⭐⭐⭐⭐⭐
Processing Time        2.1 days  <3 days   ⭐⭐⭐⭐⭐
Collection Rate        96.5%     >95%      ⭐⭐⭐⭐⭐
GOP Variance          +$5,060   >$0       ⭐⭐⭐⭐⭐

Overall Score: 99/100 ⭐⭐⭐⭐⭐ EXCELLENT

═══════════════════════════════════════════════════════════

HOTEL OVERALL: 96.25/100 ⭐⭐⭐⭐⭐ EXCELLENT PERFORMANCE
═══════════════════════════════════════════════════════════
```

---

## Forecasting & Budgeting

### 5.1 Rolling Forecast (90 Days)

```
═══════════════════════════════════════════════════════════
        90-DAY ROLLING FORECAST
        January 15 - April 15, 2025
═══════════════════════════════════════════════════════════

Month      Occ%    Rooms   ADR      RevPAR   Revenue    vs Budget
──────────────────────────────────────────────────────────────────
Jan (MTD)   89%    1,379   $169    $150    $233,051    +4.2% ✅
Jan (Fcst)  87%    1,350   $168    $146    $226,800    +2.8% ✅

February    85%    1,190   $172    $146    $204,680    +1.5% ✅
March       88%    1,364   $175    $154    $238,700    +3.8% ✅
April       82%    1,230   $165    $135    $202,950    -1.2% ⚠️

Q1 Forecast 86%    5,134   $170    $146    $873,180    +2.5% ✅
──────────────────────────────────────────────────────────────────

KEY DRIVERS:
├─ January: Strong holiday carryover
├─ February: Valentine's Day boost
├─ March: Spring break demand
└─ April: Softer corporate travel

RISKS & OPPORTUNITIES:
⚠️ Risk: April corporate slowdown
✅ Opportunity: Group bookings in March
⚠️ Risk: Comp set aggressive pricing
✅ Opportunity: Direct booking growth

═══════════════════════════════════════════════════════════
```

---

### 5.2 Budget vs. Actual Analysis

```
═══════════════════════════════════════════════════════════
        BUDGET vs. ACTUAL ANALYSIS
        January 2025 (Month-to-Date)
═══════════════════════════════════════════════════════════

REVENUE ANALYSIS
─────────────────────────────────────────────────────────
                    Budget      Actual     Variance    %
─────────────────────────────────────────────────────────
Room Revenue       $230,000   $240,000    +$10,000   +4.3%
F&B Revenue        $65,000    $67,000     +$2,000    +3.1%
Other Revenue      $15,000    $15,600     +$600      +4.0%
─────────────────────────────────────────────────────────
TOTAL REVENUE      $310,000   $322,600    +$12,600   +4.1%

EXPENSE ANALYSIS
─────────────────────────────────────────────────────────
                    Budget      Actual     Variance    %
─────────────────────────────────────────────────────────
Rooms Expense      $45,000    $46,680     +$1,680    +3.7%
F&B Expense        $52,000    $52,930     +$930      +1.8%
Other Depts        $9,500     $9,000      -$500      -5.3%
Undistributed      $85,000    $83,930     -$1,070    -1.3%
─────────────────────────────────────────────────────────
TOTAL EXPENSE      $191,500   $192,540    +$1,040    +0.5%

PROFITABILITY
─────────────────────────────────────────────────────────
GOP                $118,500   $130,060    +$11,560   +9.8%
GOP Margin         38.2%      40.3%       +2.1pts    ✅

NOI                $80,000    $86,509     +$6,509    +8.1%
NOI Margin         25.8%      26.8%       +1.0pt     ✅

═══════════════════════════════════════════════════════════

VARIANCE COMMENTARY:

Favorable Variances (✅):
1. Room Revenue: +$10K (+4.3%)
   → Higher occupancy (89% vs. 85% budget)
   → Better rate realization ($169 vs. $165)

2. GOP: +$11.6K (+9.8%)
   → Revenue exceeded expectations
   → Good cost control in undistributed expenses

3. Undistributed Expense: -$1.1K (-1.3%)
   → Utilities savings from efficiency measures
   → Marketing ROI improved

Unfavorable Variances (⚠️):
1. Rooms Expense: +$1.7K (+3.7%)
   → Higher occupancy drove more costs
   → Still within acceptable range

2. F&B Expense: +$0.9K (+1.8%)
   → Aligned with higher revenue
   → Cost % maintained

OVERALL ASSESSMENT: Strong Performance ⭐⭐⭐⭐⭐
═══════════════════════════════════════════════════════════
```

---

## Custom Reports

### 6.1 Creating Custom Reports

**Report Builder:**

```
Reports → Custom Reports → Create New

Step 1: Select Data Sources
☑ Reservations
☑ Financial Transactions
☑ Guest Profiles
☑ Room Status
☐ Housekeeping Tasks
☐ F&B Transactions

Step 2: Choose Dimensions
☑ Date Range
☑ Room Type
☑ Market Segment
☑ Rate Type
☐ Guest Nationality
☐ Booking Source

Step 3: Select Metrics
☑ Revenue
☑ Occupancy
☑ ADR
☑ RevPAR
☐ Length of Stay
☐ Lead Time

Step 4: Filters
Date Range: [Last 30 days]
Room Type: [All]
Market Segment: [Corporate, Transient]

Step 5: Visualization
Chart Type: [Line Chart] / [Bar Chart] / [Table]
Group By: [Date]
Sort By: [Date Ascending]

Step 6: Schedule (Optional)
☑ Email Report Automatically
Frequency: [Daily] / [Weekly] / [Monthly]
Recipients: [gm@hotel.com, finance@hotel.com]
Time: [06:00 AM]

[Generate Report] [Save Template]
```

---

### 6.2 Executive Summary Report (GM Weekly)

```
═══════════════════════════════════════════════════════════
        EXECUTIVE SUMMARY REPORT
        Week of January 8-14, 2025
        Grand Canyon Hotel
═══════════════════════════════════════════════════════════

📊 WEEK HIGHLIGHTS

Performance vs. Budget:
├─ Revenue: +5.2% ✅
├─ GOP: +7.8% ✅
├─ Occupancy: +2.1 pts ✅
└─ ADR: +$8.50 ✅

Performance vs. Last Year:
├─ Revenue: +8.1% ✅
├─ GOP: +9.5% ✅
├─ RevPAR: +12.3% ✅
└─ Guest Satisfaction: +0.4 pts ✅

═══════════════════════════════════════════════════════════

📈 KEY METRICS

                    This Week   Last Week   Change
──────────────────────────────────────────────────────
Occupancy            88.5%       86.2%      +2.3 pts
ADR                  $171.20     $168.40    +$2.80
RevPAR               $151.51     $145.20    +$6.31
GOP                  $52,300     $48,900    +$3,400
GOP Margin           41.2%       40.1%      +1.1 pts

═══════════════════════════════════════════════════════════

🎯 OPERATIONAL HIGHLIGHTS

Wins:
✅ Highest occupancy week of the month (88.5%)
✅ Successfully managed group check-in (25 rooms)
✅ Zero guest complaints in F&B
✅ Reduced check-in time to 4.1 minutes

Challenges:
⚠️ 2 maintenance issues (rooms 305, 412)
⚠️ Housekeeping overtime (15 hours total)
⚠️ One no-show (corporate booking)

═══════════════════════════════════════════════════════════

📅 NEXT WEEK OUTLOOK

Forecast:
├─ Expected Occupancy: 92%
├─ Expected ADR: $178
├─ Expected RevPAR: $164
└─ Expected GOP: $56,000

Events:
├─ Jan 18: City Marathon (high demand)
├─ Jan 19: Corporate group arrival (12 rooms)
└─ Jan 21: VIP guest arrival

Action Items:
1. Implement peak pricing for Jan 18-19
2. Prepare VIP amenities for Suite 601
3. Schedule staff overtime for marathon weekend
4. Monitor comp set pricing daily

═══════════════════════════════════════════════════════════

💡 RECOMMENDATIONS

1. 📈 REVENUE
   Consider increasing weekend rates by $15-20
   Opportunity: High demand, limited comp set availability

2. 💰 COST CONTROL
   Review housekeeping schedules to reduce overtime
   Potential savings: $500-700/week

3. 🎯 MARKETING
   Launch "Valentine's Day Package" promotion
   Target: Direct bookings, increase ADR

4. 👥 STAFFING
   Hire 2 additional housekeeping staff for peak season
   ROI: Better service quality, reduced overtime

═══════════════════════════════════════════════════════════

Prepared by: Finance Department
Date: January 15, 2025, 06:00 AM
Next Report: January 22, 2025
═══════════════════════════════════════════════════════════
```

---

## Best Practices & Tips

### 📊 Daily Routine (GM/Revenue Manager)

```
Morning (06:00 - 10:00):
├─ 06:00: Review Daily Flash Report
├─ 06:15: Check overnight occupancy
├─ 06:30: Review competitor pricing
├─ 07:00: Adjust rates if needed
├─ 08:00: Department heads meeting
└─ 09:00: Review guest feedback

Afternoon (14:00 - 16:00):
├─ 14:00: Review pickup pace
├─ 14:30: Check reservations forecast
├─ 15:00: Financial reports review
└─ 15:30: Revenue strategy meeting

Evening (17:00 - 18:00):
├─ 17:00: Check tomorrow's arrivals
├─ 17:30: Brief night shift
└─ 18:00: Final rate adjustments
```

---

### 💡 Key Success Factors

```
1. DATA-DRIVEN DECISIONS
   ✅ Use reports, not gut feeling
   ✅ Track metrics consistently
   ✅ Compare vs. comp set, budget, LY
   ✅ Act on insights quickly

2. FORWARD LOOKING
   ✅ Focus on future, not just past
   ✅ Monitor pickup pace daily
   ✅ Adjust strategy proactively
   ✅ Anticipate demand changes

3. BALANCED APPROACH
   ✅ Revenue AND profitability
   ✅ Guest satisfaction AND efficiency
   ✅ Short-term AND long-term
   ✅ All departments, not just rooms

4. TEAM COLLABORATION
   ✅ Share reports with teams
   ✅ Celebrate wins together
   ✅ Address challenges collectively
   ✅ Continuous improvement mindset
```

---

## 🎓 Certification & Next Steps

**Congratulations!** You've completed the Management Dashboard & Reporting training.

**You've learned:**
- ✅ Executive Dashboard navigation
- ✅ Financial reporting & analysis
- ✅ Revenue management strategies
- ✅ Operational analytics
- ✅ Forecasting & budgeting
- ✅ Custom report creation

**Next steps:**
1. Practice with live system (training mode)
2. Schedule weekly report reviews
3. Set up automated report emails
4. Advanced: Predictive analytics training

---

**Doküman güncellenme tarihi:** 15 Ocak 2025
**Versiyon:** 1.0
