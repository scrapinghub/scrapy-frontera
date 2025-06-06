from pathlib import Path

from setuptools import find_packages, setup

setup(
    name="scrapy-frontera",
    description="Featured Frontera scheduler for Scrapy",
    long_description=Path("README.rst").read_text(),
    version="0.3.0",
    licence="BSD",
    url="https://github.com/scrapinghub/scrapy-frontera",
    maintainer="Scrapinghub",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=(
        "frontera>=0.7.2,<0.8",
        "scrapy>=2.7.0",
        "w3lib>=1.17.0",
    ),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
