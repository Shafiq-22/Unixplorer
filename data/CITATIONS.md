# Data citations and acknowledgements

Each block quotes the archive's required acknowledgement text exactly as it appeared on the
linked page on the retrieval date. Do not paraphrase. If a page changes, re-copy it and update
the date.

## Gaia DR3: `gaia_dr3_nearby`, `gaia_dr3_distances` (join side)

Source: https://gea.esac.esa.int/archive/documentation/GDR3/Miscellaneous/sec_credit_and_citation_instructions/
(retrieved 2026-10-12)

> This work has made use of data from the European Space Agency (ESA) mission Gaia
> (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing and Analysis
> Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC
> has been provided by national institutions, in particular the institutions participating in the
> Gaia Multilateral Agreement.

The same page asks users to cite "both the Gaia mission paper and the Gaia DR3 release paper":
Gaia Collaboration et al. (2016b), *The Gaia mission*, and Gaia Collaboration et al. (2023j),
*Gaia DR3: Summary of the contents and survey properties*. Those bibcodes are not recorded here
yet. Add them once they are resolved in NASA ADS.

## Bailer-Jones et al. (2021) distances: `gaia_dr3_distances`

Reference as given by the CDS catalogue ReadMe for I/352
(https://cdsarc.cds.unistra.fr/ftp/I/352/ReadMe, retrieved 2026-10-12):

> Bailer-Jones C.A.L., Rybizki J., Fouesneau M., Demleitner M., Andrae R.
> <Astron. J. 161, 147 (2021)>
> =2021AJ....161..147B

Status: bibcode taken from CDS. Confirming it against NASA ADS is still pending because the ADS
API needs a token (§8.3).

## SIMBAD: `simbad_ids`, `landmarks`

Source: https://cds.unistra.fr/help/acknowledgement/ (retrieved 2026-10-12)

> This research has made use of the SIMBAD database, CDS, Strasbourg Astronomical Observatory,
> France

Reference given on the same page: 2000, A&AS, 143, 9, "The SIMBAD astronomical database",
Wenger et al.

## NASA Exoplanet Archive: `exoplanets_ps`

Source: https://exoplanetarchive.ipac.caltech.edu/docs/acknowledge.html (retrieved 2026-10-12)

> This research has made use of the NASA Exoplanet Archive, which is operated by the California
> Institute of Technology, under contract with the National Aeronautics and Space Administration
> under the Exoplanet Exploration Program.

The same page adds: "In addition, if you use data from a specific literature reference, please
acknowledge that reference directly." Each `ps` row's own reference must therefore be cited
wherever that row's values are shown. It also asks users to cite Christiansen et al. (2025) as
the archive's reference paper; that bibcode is not recorded yet.

## JPL Horizons: `horizons_bodies`

Source: https://ssd.jpl.nasa.gov/horizons/manual.html (manual version 4.98e, retrieved
2026-10-12). The manual gives no required acknowledgement text. Its "Acknowledgements" section
credits the JPL staff who built the system. Cite as: JPL Horizons On-Line Ephemeris System,
Solar System Dynamics Group, Jet Propulsion Laboratory, https://ssd.jpl.nasa.gov/horizons/.
The ephemeris source recorded in each response is DE441, and PLU060/DE440 for Pluto and Charon.

## `galaxy_structure`

Not fetched: a model paper has not been chosen yet.
