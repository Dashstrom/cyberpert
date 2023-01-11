from setuptools import find_packages, setup


def read(path):
    # type: (str) -> str
    with open(path, "rt", encoding="utf8") as f:
        return f.read().strip()


setup(
    name="cyberpert",
    version="1.0.0.dev20230111",
    author="Dashstrom",
    author_email="dashstrom.pro@gmail.com",
    url="https://github.com/Dashstrom/cyberpert",
    license="GPL-3.0 License",
    packages=find_packages(exclude=("tests",)),
    description="Find cves throw dependencies.",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    python_requires=">=3.6.0",
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
    ],
    test_suite="tests",
    keywords=["system", "expert", "data", "pypi", "cve", "audit"],
    install_requires=read("requirements.txt").split("\n"),
    platforms="any",
    include_package_data=True,
    package_data={
        "cyberpert": ["py.typed", "data/rules.json.zip"],
    },
    entry_points={
        "console_scripts": [
            "cyberpert=cyberpert.cli:app",
        ]
    },
)
