from setuptools import setup, find_packages

setup(
    name="pandasql",
    version="0.8.0",
    author="Michael Dempsey",
    author_email="bluestealth@bluestealth.pw",
    url="https://github.com/bluestealth/pandasql/",
    license="MIT",
    packages=find_packages(),
    package_dir={"pandasql": "pandasql"},
    package_data={"pandasql": ["data/*.csv"]},
    description="sqldf for pandas",
    long_description=open("README.rst").read(),
    install_requires=["numpy", "pandas", "sqlalchemy", "packaging"],
    classifiers=[
        "License :: OSI Approved :: MIT License",
    ],
)
