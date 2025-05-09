from setuptools import setup, find_packages

setup(
    name="dingo-command",
    version="0.1.0",
    description="Dingo Command Project",
    packages=find_packages(),
    package_dir={"dingo-command": "dingo-command"},
    python_requires=">=3.6",
    install_requires=[
        "oslo.config",
        "alembic",
        "sqlalchemy",
        "databases",
        "pymysql",
    ],
)
