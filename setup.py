from setuptools import setup

setup(
    name="valorant_model",
    version="2.0.0",
    # Tell setuptools: the current directory IS the valorant_model package.
    # This makes `import valorant_model` work after `pip install -e .`
    # even when setup.py lives inside the package directory itself.
    package_dir={
        "valorant_model":            ".",
        "valorant_model.data":       "data",
        "valorant_model.features":   "features",
        "valorant_model.models":     "models",
        "valorant_model.simulation": "simulation",
        "valorant_model.utils":      "utils",
    },
    packages=[
        "valorant_model",
        "valorant_model.data",
        "valorant_model.features",
        "valorant_model.models",
        "valorant_model.simulation",
        "valorant_model.utils",
    ],
    install_requires=[
        "numpy>=1.26.0",
        "pandas>=2.1.0",
        "scipy>=1.11.0",
        "rich>=13.7.0",
        "openpyxl>=3.1.0",
    ],
    entry_points={
        "console_scripts": [
            "val=valorant_model.main:main",
        ],
    },
    python_requires=">=3.10",
)
