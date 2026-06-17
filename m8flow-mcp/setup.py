#!/usr/bin/env python3
"""Setup script for m8flow-mcp package distribution."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="m8flow-mcp",
    version="1.0.0",
    description="Model Context Protocol server for m8flow workflow management",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="AOT Technologies",
    author_email="support@aot-technologies.com",
    url="https://github.com/AOT-Technologies/m8flow-mcp",
    license="Apache-2.0",

    # Package discovery
    packages=find_packages(include=["src", "src.*"]),
    package_dir={"": "."},

    # Dependencies
    install_requires=[
        "fastmcp>=0.3.0",
        "httpx>=0.27.0",
        "pydantic>=2.0",
        "pydantic-settings>=2.0",
        "python-jose[cryptography]>=3.3.0",
        "python-multipart>=0.0.9",
        "uvicorn>=0.30.0",
    ],

    # Extra dependencies for development
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.23",
            "pytest-cov>=5.0",
            "ruff>=0.3",
            "mypy>=1.9",
        ]
    },

    # Python version requirement
    python_requires=">=3.12",

    # Entry point for CLI command
    entry_points={
        "console_scripts": [
            "m8flow-mcp=src.main:main",
        ],
    },

    # PyPI classifiers
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],

    # Include non-Python files
    include_package_data=True,
    zip_safe=False,
)
