Frontera scheduler for Scrapy
=============================

More flexible and featured frontera scheduler for scrapy, which don't force to reimplement capabilities already present in scrapy

- A request dupefilter (using same scrapy DUPEFILTER_CLASS setting)
- Allows to set frontera settings from spider constructor, by loading frontera manager after spider instantiation.
- Allows frontera components to access scrapy stat manager instance by adding STATS_MANAGER frontera setting
- Better request/response converters

Usage:
------

In your project settings.py::

    SCHEDULER = 'scrapy_frontera.scheduler.FronteraScheduler'

Plus the usual frontera setup
