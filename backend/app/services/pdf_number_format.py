"""Indian digit-grouping (lakh/crore style: 12,34,567.89, not the
international 1,234,567.89) for amounts rendered into PDF exports. Mirrors
the frontend's formatMoney (ui.jsx), which gets this for free from
`toLocaleString("en-IN")` - Python has no equivalent locale-independent
built-in, so it's done by hand here."""


def format_inr(value) -> str:
    n = float(value or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole, _, frac = f"{n:.2f}".partition(".")

    if len(whole) <= 3:
        grouped = whole
    else:
        last3 = whole[-3:]
        rest = whole[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3

    return f"{sign}{grouped}.{frac}"
