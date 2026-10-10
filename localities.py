"""Locality test set for the stage-indexed lookup (Delhi, July 2023).

Fixed and committed on 2026-10-10 BEFORE the stage library was read or
scored. Coordinates are OpenStreetMap Nominatim results (2026-10-10).
See PREREG_LOCALITIES.md for the rules.

label:
  "river"  recorded as submerged in July 2023 and on the river side of the
           city, so river overflow is the plausible cause
  "drain"  recorded as flooded, but attributed to drain backflow or a
           regulator failure, which the model does not represent
  "dry"    no record of Yamuna flooding found (absence of a report, which
           is weaker evidence than a record of staying dry)
source: where the 2023 label comes from.
"""

LOCALITIES = [
    # name, lat, lon, label, source
    ("Yamuna Bazar", 28.66200, 77.23938, "river", "NIDM 2024 proceedings"),
    ("Nigam Bodh Ghat", 28.66482, 77.23658, "river", "NIDM 2024 proceedings"),
    ("Vijay Ghat", 28.65593, 77.24710, "river", "NIDM 2024 proceedings"),
    ("Usmanpur", 28.68385, 77.25601, "river", "NIDM 2024 proceedings"),
    ("Majnu ka Tilla", 28.70434, 77.22449, "river", "Times of India"),
    ("Kashmere Gate ISBT", 28.66870, 77.23042, "river", "Times of India"),
    ("Bela Road, Civil Lines", 28.67756, 77.22955, "river",
     "Sphere India sitrep (Civil Lines)"),
    ("Raj Ghat", 28.64415, 77.24984, "drain", "ThePrint, NDTV (drain 12)"),
    ("ITO", 28.62819, 77.24104, "drain", "NDTV (drain 12 regulator)"),
    ("Hakikat Nagar", 28.69852, 77.20856, "drain",
     "NIDM 2024 proceedings (backflow in colonies)"),
    ("Geeta Colony", 28.65109, 77.27500, "dry", "no report found"),
    ("Laxmi Nagar", 28.63060, 77.27752, "dry", "no report found"),
    ("Gandhi Nagar", 28.65879, 77.27159, "dry", "no report found"),
    ("Seelampur", 28.66982, 77.26681, "dry", "no report found"),
    ("Chandni Chowk", 28.65598, 77.23219, "dry", "no report found"),
    ("Daryaganj", 28.64609, 77.24305, "dry", "no report found"),
    ("Connaught Place", 28.63177, 77.21938, "dry", "no report found"),
    ("Kamla Nagar", 28.68068, 77.20395, "dry", "no report found"),
    ("DU North Campus", 28.69249, 77.21818, "dry", "no report found"),
    ("Paharganj", 28.64150, 77.21406, "dry", "no report found"),
]
