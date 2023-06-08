import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

REQUIREMENTS = [
    "kubernetes",
    "click",
    "ansicolors",
    "jsonpath_ng",
    "pandas",
    "tabulate",
]

DEV_REQUIREMENTS = [
    'black == 23.*',
    'build == 0.10.*',
    'flake8 == 6.*',
    'isort == 5.*',
    'mypy == 1.2',
    'pytest == 7.*',
    'pytest-cov == 4.*',
    'twine == 4.*',
]

setuptools.setup(
    name='python-kubectl-query',
    version='0.2.0',
    description='Query multiple cluster resources and join them together as tables',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='http://github.com/gunther788/python-kubectl-query',
    author='gunther788',
    license='MIT',
    packages=setuptools.find_packages(
        exclude=[
            'test',
        ]
    ),
    include_package_data=True,
    package_data={
        'kubectl_query': [
            'py.typed',
            'config/*.yaml',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=REQUIREMENTS,
    extras_require={
        'dev': DEV_REQUIREMENTS,
    },
    entry_points={
        'console_scripts': [
            'kubectl-query=kubectl_query:main',
        ]
    },
    python_requires='>=3.9, <4',
)
