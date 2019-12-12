import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="metarace",
    version="2.0.1",
    author="Nathan Fraser",
    author_email="ndf@metarace.com.au",
    url="https://github.com/ndf-zz/metarace",
    description="Cycle race abstractions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        'Topic :: Other/Nonlisted Topic',
    ],
    python_requires='>=3.0',
    zip_safe=True,
    install_requires=[ 
      'serial', 'rsvg', 'cairo', 'pango', 'pangocairo', 'xlwt',
    ],
)

