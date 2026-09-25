"""What the world measured, from the people who measure it.

A parametric policy's whole claim is that nobody decides whether it pays. An
index is read, a ladder is applied, and the money moves. That claim is only
worth as much as the reading behind it, and until now the reading came from
inside this protocol: the chain generated it. Every source this codebase named
-- USGS, EMSC, GFZ, AFAD, JMA, INGV -- was recorded as provenance rather than
read as data. This package is the part that goes and asks them.

Four rules shape it, and each of them is here because somebody else learned it
the expensive way.

**A reading is never just a number.** It is a number, the moment the world
made it, the moment the source published it, the moment we fetched it, the
exact query we sent, and a digest of the bytes that came back. A payout a
person cannot check is a payout they have to trust, and this protocol's entire
argument is that they should not have to.

**Sources disagree, and the disagreement is not noise.** For the Pazarcik
earthquake of 6 February 2023, USGS says magnitude 7.8 and AFAD says 7.7. For
Elbistan the same morning, USGS and EMSC say 7.5 and AFAD says 7.6. A policy
written at 7.6 pays on one official source and not on another. So a reading is
taken from more than one source where more than one exists, the spread is
recorded, and a spread wider than the peril's tolerance holds the settlement
instead of quietly picking a side.

**"Finally revised" never arrives.** USGS was still revising the magnitude of
the 7.8 Kahramanmaras earthquake on 13 April 2026, three years and two months
after it happened; the 7.5 was revised in August 2026. A contract that settles
on the final value settles never. So each peril names a window -- so many hours
after the event -- and settles on what the source said at the end of it. A
revision that lands later is recorded against the policy and does not claw the
money back, and the contract says so before it is bought.

**An instrument with money on it is a target.** In April 2026 the temperature
readings at Meteo-France's Paris Charles de Gaulle station jumped four and five
degrees on two evenings, each time setting a site record and diverging from
every neighbouring station, and each time settling money on a prediction
market. French prosecutors opened an investigation. The defences that worked
were not cryptographic: a reading corroborated across sources, a gridded
product rather than a single gauge, a named backup and a published rule for
switching to it. All three are in here.
"""

from .observation import Observation, Reading, digest_of
from .agreement import Agreement, agree

__all__ = ["Observation", "Reading", "Agreement", "agree", "digest_of"]
