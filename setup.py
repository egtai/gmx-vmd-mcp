from setuptools import setup, find_packages

setup(
    name="mcp-gmx-vmd",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "mcp>=1.4.1",
        "numpy>=2.0.0",
        "matplotlib>=3.5.0",
        "psutil>=5.9.0",
        "fastapi>=0.100.0",
        "uvicorn>=0.20.0",
        "pydantic>=2.0.0",
        "requests>=2.28.0",
        "typer>=0.9.0",
        "rich>=13.0.0",
    ],
    entry_points={
        "console_scripts": [
            "mcp-gmx-vmd=mcp_gmx_vmd.main:main",
        ],
    },
    author="MCP Team",
    author_email="example@example.com",
    description="MCP service for GROMACS and VMD molecular dynamics simulations and visualization",
    keywords="molecular dynamics, gromacs, vmd, simulation, visualization",
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
) 