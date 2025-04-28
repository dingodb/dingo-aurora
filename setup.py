from setuptools import setup, find_packages

setup(
    name="dingoops",
    version="0.1.0",
    description="DingoOps Project",
    packages=find_packages(),
    package_dir={"dingoops": "dingoops"},
    python_requires=">=3.6",
    install_requires=[
        "oslo.config",
        "alembic",
        "sqlalchemy",
        "databases",
        "pymysql",
    ],
)
