"""
Self-contained setuptools configuration for MOFinder.

Two installation paths are supported, and they intentionally produce the same result:

    1. PEP 517/621 (preferred):   pip install .
       — reads pyproject.toml; setup.py is not needed.

    2. Legacy / explicit:         python setup.py install   (or develop)
       — reads this file directly; pyproject.toml is not needed.

If both files exist (the default in this repo), pip will use pyproject.toml.
This setup.py is kept complete so the project can also be built with the
classic setuptools workflow, e.g. on machines where PEP 517 builds are
restricted or where users prefer `python setup.py develop`.

Keep the metadata here in sync with pyproject.toml.
"""

from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).parent
LONG_DESCRIPTION = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""


# Core runtime dependencies — what every numbered step assumes is importable.
INSTALL_REQUIRES = [
    # data / numerics
    "pandas>=1.5",
    "numpy>=1.23",
    "matplotlib>=3.6",
    "scikit-learn>=1.2",

    # LLM client + schema
    "openai>=1.40",
    "pydantic>=2.0",
    "tiktoken>=0.5",

    # paper / SI ingestion
    "pypdf>=4.0",
    "openpyxl>=3.1",

    # utility
    "requests>=2.28",
    "tqdm>=4.64",
    "rich>=13.0",
    "python-dotenv>=1.0",
    "ipywidgets>=8.0",
]


EXTRAS_REQUIRE = {
    # Tk + image-based downloader used by step 2.1 / 2.2 (Windows-friendly; needs a desktop session).
    "fetch-gui": [
        "pyautogui>=0.9.54",
        "pyperclip>=1.8",
        "pynput>=1.7",
        "opencv-python>=4.7",
    ],

    # Selenium stack — used by SMILESearcher (ChemSpider, Google AI Overview, etc.).
    "fetch-web": [
        "selenium>=4.10",
        "webdriver-manager>=4.0",
    ],

    # Chemistry-aware SMILES validation. SMILESearcher falls back to a heuristic check
    # if rdkit is unavailable. Install separately if pip wheels are unstable on your platform.
    "chem": [
        "rdkit>=2023.3",
    ],

    # Notebook UX. The numbered step notebooks are usable without JupyterLab
    # if you prefer VS Code / nbclient.
    "notebook": [
        "jupyterlab>=4.0",
        "notebook>=7.0",
    ],
}

# `all` aggregates every optional group so `pip install .[all]` matches
# the original step-0 `pip install ...` one-liner.
EXTRAS_REQUIRE["all"] = sorted(
    {pkg for group in EXTRAS_REQUIRE.values() for pkg in group})


setup(
    name="MOFinder",
    version="0.1.0",
    description=(
        "Literature-mining and LLM fine-tuning pipeline for "
        "Metal-Organic Framework (MOF) synthesis prediction."
    ),
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author="ZZhengLab @WashU and Gao @Penn",
    url="https://github.com/zzhenglab/MOFinder",
    license="MIT License",
    keywords=[
        "metal-organic-framework",
        "MOF",
        "synthesizability",
        "literature-mining",
        "large-language-model",
        "Agentic AI",
        "Materials Science",
        "chemistry",
    ],
    classifiers=[
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    # The repository is currently organized as numbered notebooks at the repo root
    # plus the self-contained SMILESearcher/ utility. Only the SMILESearcher tree
    # is packaged so its modules remain importable; the notebooks are run in place.
    packages=find_packages(
        where=".",
        include=["SMILESearcher*"],
        exclude=["downloaded*", "mof_json_store*"],
    ),
    include_package_data=True,
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS_REQUIRE,
)
