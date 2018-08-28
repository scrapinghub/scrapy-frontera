from setuptools import setup, find_packages

setup(
    name         = 'scrapy-frontera',
    description  = 'Featured Frontera scheduler for Scrapy',
    version      = '0.2.2',
    licence      = 'BSD',
    url          = 'https://github.com/scrapinghub/hcf-backend',
    author_email = 'info@scrapinghub.com',
    maintainer   = 'Scrapinghub',
    maintainer_email = 'info@scrapinghub.com',
    packages     = find_packages(),
    install_requires=('frontera==0.7.1',),
    classifiers = [
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ]
)
