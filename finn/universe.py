"""Demo universe: the mock portfolio and the ad-hoc research set.

The engine is not tied to these lists — any NSE symbol that screener.in covers
works in Pull (research) and can be added to the portfolio.
"""

PORTFOLIO = [
    # symbol, sector, size bucket
    ("RELIANCE", "Conglomerate", "Large"),
    ("HDFCBANK", "Private bank", "Large"),
    ("INFY", "IT services", "Large"),
    ("LT", "Engineering & infra", "Large"),
    ("BAJFINANCE", "Consumer lending", "Large"),
    ("SUNPHARMA", "Pharma", "Large"),
    ("TITAN", "Consumer", "Large"),
    ("MARUTI", "Autos", "Large"),
    ("APOLLOHOSP", "Healthcare", "Large"),
    ("PIIND", "Agrochem / specialty chem", "Mid"),
    ("NAVINFLUOR", "Specialty chemicals", "Mid"),
    ("AARTIIND", "Specialty chemicals", "Mid"),
    ("DIXON", "Electronics manufacturing", "Mid"),
    ("KAYNES", "Electronics / semis", "Mid"),
    ("CGPOWER", "Industrials / semis", "Mid"),
    ("PERSISTENT", "IT services", "Mid"),
    ("CREDITACC", "Rural lending (MFI)", "Mid"),
    ("EQUITASBNK", "Small finance bank", "Small"),
    ("SUBEXLTD", "Telecom software", "Small"),
]

RESEARCH = ["SRF", "POLYCAB", "ETERNAL", "ASIANPAINT"]
