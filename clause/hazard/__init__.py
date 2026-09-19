"""Earthquake hazard beyond Türkiye: a gridded model per country, built from the
public catalogue, tested on years it never saw, and published with its record.

The Turkish model in ``clause.perils.geo`` is hand built from named faults. That
does not scale to a hundred countries, and it should not have to: what a
parametric earthquake policy needs is the rate of events of each magnitude
inside a circle, and the instrumental catalogue measures exactly that. So every
other country is modelled the same way, from the same data, by the same code:

    catalogue   USGS ComCat, magnitude 4.5 and above since 1973, public domain
    declustered Gardner and Knopoff windows, so aftershocks are not counted as
                independent events and a single large earthquake does not
                inflate the rate of its neighbourhood for decades
    rates       smoothed seismicity on a 0.1 degree grid (a Gaussian kernel),
                with a small uniform floor so no cell is priced at zero
    sizes       truncated Gutenberg and Richter, b value fitted per country by
                maximum likelihood, maximum magnitude from the record
    tested      fitted on the years up to 2010, scored on 2011 onward, and only
                published for a country that passes

A country with no model here is not priced, whatever the registry says. That is
the point of the rest of this package.
"""

# The runtime model is imported from .model; the build tools stand alone.
