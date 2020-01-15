from setuptools import setup, find_packages

setup(
    name         = 'scrapy-frontera',
    description  = 'Featured Frontera scheduler for Scrapy',
    long_description = open('README.rst').read(),
    version      = '0.2.8.1',
    licence      = 'BSD',
    url          = 'https://github.com/scrapinghub/scrapy-frontera',
    maintainer   = 'Scrapinghub',
    packages     = find_packages(),
    install_requires=(
        'frontera==0.7.1',
        'scrapy',
    ),
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ]
)
