from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in brainfel/__init__.py
from brainfel import __version__ as version

setup(
	name="brainfel",
	version=version,
	description="FEL GT 4 ERPCH",
	author="CHAPPSA",
	author_email="soporte@chappsa.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
