
import datetime as _dt

# A departure two weeks out: flight subjects must name a date that is still
# ahead, whenever the suite runs.
FLIGHT_DATE = (_dt.date.today() + _dt.timedelta(days=14)).isoformat()
