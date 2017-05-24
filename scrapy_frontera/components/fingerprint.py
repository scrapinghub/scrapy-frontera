from frontera.contrib.middlewares.fingerprint import UrlFingerprintMiddleware as FronteraUrlFingerprintMiddleware

class UrlFingerprintMiddleware(FronteraUrlFingerprintMiddleware):
    def add_seeds(self, seeds):
        for seed in seeds:
            self._add_fingerprint(seed)
            yield seed
