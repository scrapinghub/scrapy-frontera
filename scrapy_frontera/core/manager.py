from frontera.core.manager import (
    FrontierManager as FronteraFrontierManager,
)
from frontera.settings import Settings

from scrapy_frontera.settings import DEFAULT_SETTINGS


class FrontierManager(FronteraFrontierManager):
    @classmethod
    def from_settings(cls, settings=None):
        """
        Returns a :class:`FrontierManager <frontera.core.manager.FrontierManager>`  instance initialized with \
        the passed settings argument. If no settings is given,
        :ref:`frontier default settings <frontier-default-settings>` are used.
        """
        settings = settings or Settings()
        Settings.object_from(settings)
        settings.set_from_dict(DEFAULT_SETTINGS)
        return super().from_settings(settings)
