import pathlib
from setuptools import setup, find_packages

# The directory containing this file
HERE = pathlib.Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

# This call to setup() does all the work
setup(
    name="hikvideos",
    version="1.2.1",
    description="Télécharger les enregistrements d'une caméra HikVision autonome",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/Tedyst/HikLoad",
    author="Stoica Tedy",
    author_email="stoicatedy@gmail.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    packages=find_packages(),
    include_package_data=True,
    # Versions minimales et non figées : les versions épinglées par l'amont
    # (lxml 4.9.1 notamment) ne se compilent pas sous Python 3.12.
    install_requires=[
        "ffmpeg-python>=0.2.0",
        "lxml>=5.0",
        "pyqt5>=5.15.9",
        "requests>=2.31",
        "tqdm>=4.66",
        "xmler>=0.2.0",
    ],
    entry_points={
        "console_scripts": [
            "hikvideos=hikvideos.__main__:main",
            "hikvideos-qt=hikvideos.__main__:main_ui",
        ]
    },
)
