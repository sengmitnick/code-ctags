import re

from setuptools import find_packages, setup

with open("requirements.txt") as f:
    requirements = f.read().splitlines()


with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()
    long_description = re.sub(r"\n!\[.*\]\(.*\)", "", long_description)
    long_description = re.sub(r"\n- \[.*\]\(.*\)", "", long_description)

setup(
    name="code-ctags",
    version=__version__,
    packages=find_packages(),
    include_package_data=True,
    python_requires='>=3.9',
    entry_points={
        "console_scripts": [
            "code_ctags = ctags.main:main",
        ],
    },
    description="output the labels of functions, classes, variables, etc. of all files currently downloaded to the terminal",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/paul-gauthier/aider",
)
