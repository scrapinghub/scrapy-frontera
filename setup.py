from setuptools import setup, find_packages

setup(
    name         = 'scrapy_frontera',
    version      = '0.2.1',
    packages     = find_packages(),
    install_requires=('frontera==0.7.1',)
)
