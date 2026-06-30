"""nsw-site-controls — NSW planning controls for a site, from the command line.

Pipeline (see README for the full diagram):

    location  ->  locate.py  ->  Site(point, parcel, area)
                                   |
                                   +-> lep.py   -> LEP/SEPP envelope (ArcGIS REST)
                                   +-> dcp.py   -> council DCP controls (curated YAML)
                                   |
                                   v
                               sheet.py -> Site Control Sheet (text / JSON)
"""

__version__ = "0.1.0"
